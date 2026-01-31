"""
Agent stream service for handling streaming agent interactions.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from loguru import logger

from valuecell.core.agent.connect import RemoteConnections
from valuecell.core.coordinate.orchestrator import AgentOrchestrator
from valuecell.core.task.executor import TaskExecutor
from valuecell.core.task.locator import get_task_service
from valuecell.core.task.models import TaskPattern, TaskStatus
from valuecell.core.types import UserInput, UserInputMetadata
from valuecell.utils.uuid import generate_conversation_id

_TASK_AUTORESTART_STARTED = False
_AGENT_CLASSES_PRELOADED = False


def _reasoning_log_path() -> Path:
    """Return path for a new reasoning log file: reasoning_logs/reasoning_<timestamp>.log."""
    log_dir = Path(os.getenv("REASONING_LOG_DIR", "reasoning_logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    return log_dir / f"reasoning_{ts}.log"


def _preload_agent_classes_once() -> None:
    """Preload local agent classes once to avoid Windows import lock deadlocks.

    This must run in the main thread before any async operations that might
    trigger imports in worker threads. Safe to call multiple times.
    """
    global _AGENT_CLASSES_PRELOADED
    if _AGENT_CLASSES_PRELOADED:
        return
    _AGENT_CLASSES_PRELOADED = True

    try:
        logger.info("Preloading local agent classes...")
        rc = RemoteConnections()
        rc.preload_local_agent_classes(
            names=["GridStrategyAgent", "PromptBasedStrategyAgent"]
        )
        logger.info("✓ Local agent classes preloaded")
    except Exception as e:
        logger.warning(f"✗ Failed to preload local agent classes: {e}")


class AgentStreamService:
    """Service for handling streaming agent queries."""

    def __init__(self):
        """Initialize the agent stream service."""
        # Preload agent classes before creating orchestrator to avoid
        # Windows import lock deadlocks when using thread pools
        _preload_agent_classes_once()

        self.orchestrator = AgentOrchestrator()
        logger.info("Agent stream service initialized")

    async def stream_query_agent(
        self,
        query: str,
        agent_name: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream agent responses for a given query.

        Args:
            query: User query to process
            agent_name: Optional specific agent name to use. If provided, takes precedence over query parsing.
            conversation_id: Optional conversation ID for context tracking.

        Yields:
            str: Content chunks from the agent response
        """
        log_path: Optional[Path] = None
        log_file = None
        reasoning_buffer: list[str] = []
        message_buffer: list[str] = []
        message_buffer_meta: dict = {}

        try:
            logger.info(f"Processing streaming query: {query[:100]}...")

            user_id = "default_user"
            target_agent_name = agent_name

            conversation_id = conversation_id or generate_conversation_id()

            user_input_meta = UserInputMetadata(
                user_id=user_id, conversation_id=conversation_id
            )

            user_input = UserInput(
                query=query, target_agent_name=target_agent_name, meta=user_input_meta
            )

            # Open reasoning log file (one per request)
            log_path = _reasoning_log_path()
            log_file = open(log_path, "w", encoding="utf-8")
            log_file.write(
                json.dumps(
                    {
                        "type": "session_start",
                        "query": query,
                        "conversation_id": conversation_id,
                        "agent_name": target_agent_name,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            log_file.flush()

            def flush_reasoning_block(meta: Optional[dict] = None) -> None:
                if not reasoning_buffer or log_file is None:
                    return
                try:
                    line = json.dumps(
                        {
                            "type": "reasoning_block",
                            "content": "".join(reasoning_buffer),
                            **(meta or {}),
                        },
                        ensure_ascii=False,
                    )
                    log_file.write(line + "\n")
                    log_file.flush()
                except Exception:
                    pass
                reasoning_buffer.clear()

            def flush_message_block() -> None:
                if not message_buffer or log_file is None:
                    return
                try:
                    line = json.dumps(
                        {
                            "type": "message_block",
                            "content": "".join(message_buffer),
                            **message_buffer_meta,
                        },
                        ensure_ascii=False,
                    )
                    log_file.write(line + "\n")
                    log_file.flush()
                except Exception:
                    pass
                message_buffer.clear()
                message_buffer_meta.clear()

            # Use the orchestrator's process_user_input method for streaming
            async for response_chunk in self.orchestrator.process_user_input(
                user_input
            ):
                payload = response_chunk.model_dump(exclude_none=True)
                event = payload.get("event")
                data = payload.get("data") or {}

                if log_file is not None:
                    try:
                        if event == "reasoning":
                            content = (data.get("payload") or {}).get("content")
                            if content is not None:
                                reasoning_buffer.append(content)
                        elif event == "reasoning_completed":
                            flush_message_block()
                            meta = {
                                k: data.get(k)
                                for k in (
                                    "conversation_id",
                                    "thread_id",
                                    "task_id",
                                    "agent_name",
                                )
                                if data.get(k) is not None
                            }
                            flush_reasoning_block(meta)
                        elif event == "reasoning_started":
                            flush_message_block()
                            flush_reasoning_block()
                        elif event == "message_chunk":
                            content = (data.get("payload") or {}).get("content")
                            if content is not None:
                                new_item_id = data.get("item_id")
                                if (
                                    message_buffer
                                    and message_buffer_meta.get("item_id") != new_item_id
                                ):
                                    flush_message_block()
                                if not message_buffer:
                                    message_buffer_meta.update(
                                        {
                                            k: data.get(k)
                                            for k in (
                                                "conversation_id",
                                                "thread_id",
                                                "task_id",
                                                "agent_name",
                                            )
                                            if data.get(k) is not None
                                        }
                                    )
                                    if new_item_id is not None:
                                        message_buffer_meta["item_id"] = new_item_id
                                message_buffer.append(content)
                        else:
                            flush_message_block()
                            flush_reasoning_block()
                            log_file.write(
                                json.dumps(payload, ensure_ascii=False) + "\n"
                            )
                            log_file.flush()
                            # Design-doc summary lines (docs/design.md)
                            try:
                                meta = data.get("metadata") or {}
                                pl = data.get("payload") or {}
                                if event == "super_agent_outcome":
                                    log_file.write(
                                        json.dumps(
                                            {
                                                "type": "design_super_agent_outcome",
                                                "decision": meta.get("decision"),
                                                "answer_content": meta.get(
                                                    "answer_content"
                                                ),
                                                "enriched_query": meta.get(
                                                    "enriched_query"
                                                ),
                                                "reason": meta.get("reason"),
                                            },
                                            ensure_ascii=False,
                                        )
                                        + "\n"
                                    )
                                    log_file.flush()
                                elif event == "plan_created":
                                    log_file.write(
                                        json.dumps(
                                            {
                                                "type": "design_plan_created",
                                                "plan_id": meta.get("plan_id"),
                                                "orig_query": meta.get("orig_query"),
                                                "guidance_message": meta.get(
                                                    "guidance_message"
                                                ),
                                                "tasks_summary": pl.get("content"),
                                            },
                                            ensure_ascii=False,
                                        )
                                        + "\n"
                                    )
                                    log_file.flush()
                                elif event == "plan_require_user_input":
                                    log_file.write(
                                        json.dumps(
                                            {
                                                "type": "design_plan_require_user_input",
                                                "prompt": pl.get("content"),
                                                "conversation_id": data.get(
                                                    "conversation_id"
                                                ),
                                            },
                                            ensure_ascii=False,
                                        )
                                        + "\n"
                                    )
                                    log_file.flush()
                                elif event == "task_started":
                                    log_file.write(
                                        json.dumps(
                                            {
                                                "type": "design_task_started",
                                                "task_id": data.get("task_id"),
                                                "agent_name": data.get(
                                                    "agent_name"
                                                ),
                                                "conversation_id": data.get(
                                                    "conversation_id"
                                                ),
                                            },
                                            ensure_ascii=False,
                                        )
                                        + "\n"
                                    )
                                    log_file.flush()
                                elif event == "task_completed":
                                    log_file.write(
                                        json.dumps(
                                            {
                                                "type": "design_task_completed",
                                                "task_id": data.get("task_id"),
                                                "agent_name": data.get(
                                                    "agent_name"
                                                ),
                                                "conversation_id": data.get(
                                                    "conversation_id"
                                                ),
                                            },
                                            ensure_ascii=False,
                                        )
                                        + "\n"
                                    )
                                    log_file.flush()
                            except Exception:
                                pass
                    except Exception:
                        pass
                yield payload

        except Exception as e:
            logger.error(f"Error in stream_query_agent: {str(e)}")
            if log_file is not None:
                try:
                    log_file.write(
                        json.dumps(
                            {"type": "error", "error": str(e)}, ensure_ascii=False
                        )
                        + "\n"
                    )
                    log_file.flush()
                except Exception:
                    pass
            yield f"Error processing query: {str(e)}"
        finally:
            if log_file is not None:
                try:
                    if message_buffer:
                        flush_message_block()
                    if reasoning_buffer:
                        flush_reasoning_block()
                    log_file.write(
                        json.dumps(
                            {
                                "type": "session_end",
                                "ts": datetime.now(timezone.utc).isoformat(),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    log_file.close()
                    if log_path is not None:
                        logger.debug(f"Reasoning log written to {log_path}")
                except Exception:
                    pass


async def _auto_resume_recurring_tasks(agent_service: AgentStreamService) -> None:
    """Resume persisted recurring tasks that were running before shutdown."""
    global _TASK_AUTORESTART_STARTED
    if _TASK_AUTORESTART_STARTED:
        return
    _TASK_AUTORESTART_STARTED = True

    task_service = get_task_service()
    try:
        running_tasks = await task_service.list_tasks(status=TaskStatus.RUNNING)
    except Exception:
        logger.exception("Task auto-resume: failed to load tasks from store")
        return

    candidates = [
        task for task in running_tasks if task.pattern == TaskPattern.RECURRING
    ]
    if not candidates:
        logger.info("Task auto-resume: no recurring running tasks found")
        return

    executor = agent_service.orchestrator.task_executor

    task_service = get_task_service()
    for task in candidates:
        try:
            # Reset to pending and persist so TaskExecutor sees the correct state
            task.status = TaskStatus.PENDING
            await task_service.update_task(task)

            thread_id = task.thread_id or task.task_id
            asyncio.create_task(
                _drain_execute_task(executor, task, thread_id, task_service)
            )
            logger.info(
                "Task auto-resume: scheduled recurring task {} for execution",
                task.task_id,
            )
        except Exception:
            logger.exception(
                "Task auto-resume: failed to schedule task {}", task.task_id
            )


async def _drain_execute_task(
    executor: TaskExecutor, task, thread_id: str, task_service
) -> None:
    """Execute a single task via TaskExecutor and discard produced responses."""
    try:
        async for _ in executor.execute_task(task, thread_id=thread_id, resumed=True):
            pass
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Task auto-resume: execution failed for task {}", task.task_id)
