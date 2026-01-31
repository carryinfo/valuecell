# ValueCell 推理与任务拆解设计

本文档描述代码中「推理」（reasoning）、「规划」（plan）与「任务拆解」的实现方式，以及相关数据流与事件。

---

## 1. 总览

推理在 ValueCell 中主要体现在三处：

| 环节 | 作用 | 实现位置 |
|------|------|----------|
| **SuperAgent 推理** | 意图分流：直接回答 vs 交给 Planner | `core/super_agent/`、`core/coordinate/orchestrator.py` |
| **Planner 推理** | 将用户请求拆解为可执行任务（Plan / 任务拆解） | `core/plan/` |
| **执行阶段推理** | 子 Agent 的链式思考/中间推理的流式输出 | `core/event/`（reasoning 事件）、`core/task/executor.py` |

整体流程：**用户输入 → SuperAgent 分流 → Planner 生成 ExecutionPlan（任务列表）→ TaskExecutor 按任务顺序执行 → 流式输出（含 reasoning 事件）**。

---

## 2. SuperAgent 推理（意图分流）

### 2.1 职责

- 判断用户请求是否可**直接回答**（简单、事实性、无外部工具即可）。
- 若不能直接回答，则**交给 Planner**，并生成 `enriched_query`，保留用户意图。

### 2.2 实现要点

- **入口**：仅当 `user_input.target_agent_name == SuperAgentService.name`（即用户未指定具体 Agent）时，Orchestrator 会先跑 SuperAgent（`orchestrator._handle_new_request`）。
- **模型调用**：SuperAgent 使用 `output_schema=SuperAgentOutcome`、`use_json_mode`，LLM 输出结构化决策。
- **决策类型**（`SuperAgentDecision`）：
  - `ANSWER`：直接回答，附带 `answer_content`。
  - `HANDOFF_TO_PLANNER`：转交 Planner，附带 `enriched_query` 和 `reason`。
- **流式推理**：SuperAgent 的 `agent.arun(..., stream=True)` 会先产出「推理过程」字符串，再产出最终的 `SuperAgentOutcome`。Orchestrator 把这些字符串以 **reasoning_started / reasoning / reasoning_completed** 事件流式发给前端（见下节）。

相关代码：

- `python/valuecell/core/super_agent/core.py`：`SuperAgent.run()`，`SuperAgentOutcome`、`SuperAgentDecision`。
- `python/valuecell/core/super_agent/prompts.py`：`SUPER_AGENT_INSTRUCTION`，决策规则（何时 answer、何时 handoff_to_planner）。
- `python/valuecell/core/coordinate/orchestrator.py`：`_handle_new_request` 中调用 SuperAgent、发送 reasoning 事件、根据 `decision` 决定是否进入 Planner。

---

## 3. Plan 与任务拆解（Planner）

### 3.1 职责

- 把「用户请求」（或 SuperAgent 的 `enriched_query`）变成**可执行的任务列表**（ExecutionPlan）。
- 支持：指定 Agent 直通、未指定时选 Agent、周期/定时任务、Human-in-the-Loop（缺信息时暂停并要用户确认）。

### 3.2 核心类型

- **PlannerInput**（输入）：`target_agent_name`、`query`。
- **PlannerResponse**（LLM 输出）：  
  - `tasks: List[_TaskBrief]`  
  - `adequate: bool`（信息是否足够执行）  
  - `reason`、`guidance_message`（不足时给用户的说明）
- **_TaskBrief**（规划阶段的任务摘要）：`title`、`query`、`agent_name`、`pattern`（once/recurring）、`schedule_config`。
- **ExecutionPlan**（最终计划）：`plan_id`、`conversation_id`、`user_id`、`orig_query`、`tasks: List[Task]`、`guidance_message`。

Planner 不做业务逻辑推理，只做「输入 → 结构化 JSON」的推理与校验；具体能力描述来自 `tool_get_enabled_agents` / `tool_get_agent_description`。

### 3.3 任务拆解流程

1. **PlanService.start_planning_task**  
   - 若指定了 **planner passthrough** 的 Agent，则直接 `_create_passthrough_plan`：单任务、不改写 query，不调 LLM。  
   - 否则：`ExecutionPlanner.create_plan(user_input, callback, thread_id)`。

2. **ExecutionPlanner.create_plan**  
   - 构建空的 `ExecutionPlan`（含 `plan_id`、`conversation_id`、`orig_query` 等）。  
   - 调用 `_analyze_input_and_create_tasks` 得到 `(tasks, guidance_message)`，填回 `plan.tasks` 与 `plan.guidance_message`。

3. **_analyze_input_and_create_tasks**（真正的「推理+拆解」）  
   - 懒加载 Planner 的 Agent（`get_model_for_agent("super_agent")` 等）。  
   - 调用 `agent.run(PlannerInput(...), session_id=conversation_id, ...)`，得到 `run_response`。  
   - **Human-in-the-Loop**：若 `run_response.is_paused` 且存在 `tools_requiring_user_input`，则通过 `UserInputRequest` + callback 等待用户补全，再 `agent.continue_run(...)`，直到不再暂停。  
   - 将 `run_response.content` 解析为 `PlannerResponse`；若非合法 `PlannerResponse`，返回空任务列表 + 错误类 `guidance_message`。  
   - 若 `adequate` 为 False 或 `tasks` 为空，返回空任务列表 + `guidance_message`（例如要求确认周期）。  
   - 校验 `tasks` 中每个 `agent_name` 均在 `get_planable_agent_cards()` 内，否则返回空任务 + 说明「不支持的 Agent」。  
   - 将每个 `_TaskBrief` 转成 `Task`（`_create_task`），带上 `conversation_id`、`thread_id`、`handoff_from_super_agent` 等，返回 `(tasks, guidance_message)`。

4. **任务数量策略**（见 `plan/prompts.py`）  
   - 有 `target_agent_name`：透明代理，**单任务**，query 原样传递。  
   - 无 `target_agent_name`：调用 `tool_get_enabled_agents`，选一个最匹配的 Agent，**不拆成多任务**。  
   - 周期/定时：在确认 schedule 后，将 query 转为「单次执行」表述，把时间信息放进 `schedule_config`，`pattern=recurring`。

相关代码：

- `python/valuecell/core/plan/planner.py`：`ExecutionPlanner`、`create_plan`、`_analyze_input_and_create_tasks`、`_create_task`、`tool_get_agent_description`、`tool_get_enabled_agents`。
- `python/valuecell/core/plan/models.py`：`ExecutionPlan`、`PlannerInput`、`PlannerResponse`、`_TaskBrief`。
- `python/valuecell/core/plan/service.py`：`PlanService`、passthrough 逻辑、`start_planning_task`。
- `python/valuecell/core/plan/prompts.py`：`PLANNER_INSTRUCTION`、`PLANNER_EXPECTED_OUTPUT`（JSON 格式与示例）。

---

## 4. 执行阶段的推理事件（reasoning）

### 4.1 事件类型

- `StreamResponseEvent.REASONING_STARTED`  
- `StreamResponseEvent.REASONING`（内容块）  
- `StreamResponseEvent.REASONING_COMPLETED`

用于表达「某 Agent 的链式思考/中间推理」的流式输出。

### 4.2 两处产生来源

1. **SuperAgent 推理（本地）**  
   - 在 Orchestrator 中，调用 `super_agent_service.run(user_input)` 时，若返回的是字符串则视为推理内容，逐个以 `REASONING` 事件发出；开始前发 `REASONING_STARTED`，结束后发 `REASONING_COMPLETED`。  
   - 使用统一的 `item_id`（如 `generate_uuid("reasoning")`）便于前端把同一段推理聚合展示。

2. **子 Agent 推理（远程）**  
   - 子 Agent 通过 A2A 返回的 `TaskStatusUpdateEvent` 中，若 `metadata.response_event` 为 reasoning 相关，则由 **event/router** 的 `handle_status_update` 识别（`EventPredicates.is_reasoning(response_event)`），并调用 `response_factory.reasoning(...)` 生成 `ReasoningResponse`。  
   - Executor 在 `_execute_single_task_run` 里通过 `client.send_message` 收流，经 `event_service.route_task_status` 得到 `RouteResult`，其中的 `responses` 可能包含 reasoning 事件，再经 `ScheduledTaskResultAccumulator` 时 reasoning 被过滤掉不写入调度结果，但会正常向前端流式输出。

相关代码：

- `python/valuecell/core/coordinate/orchestrator.py`：SuperAgent 的 reasoning 三件套发送。  
- `python/valuecell/core/event/router.py`：`handle_status_update` 中对 `is_reasoning` 的分支。  
- `python/valuecell/core/event/factory.py`：`reasoning()` 构造 `ReasoningResponse`。  
- `python/valuecell/core/agent/responses.py`：`EventPredicates.is_reasoning`。  
- `python/valuecell/core/types.py`：`StreamResponseEvent.REASONING_*`、`ReasoningResponse`。

---

## 5. Human-in-the-Loop 与 plan_require_user_input

- Planner 在需要用户补全信息时（如确认周期、补全必填项），通过 Agno 的 `tools_requiring_user_input` 与 **UserInputRequest** 挂起：  
  - `UserInputRequest(prompt)`，`await user_input_callback(request)`，再 `await request.wait_for_response()` 得到用户输入后 `continue_run`。
- PlanService 侧用 **UserInputRegistry** 按 `conversation_id` 记录 pending 的 `UserInputRequest`。
- Orchestrator 在 **\_monitor_planning_task** 中轮询 `plan_service.has_pending_request(conversation_id)`：  
  - 若有，则保存 `ExecutionContext(stage="planning", ...)`，把 conversation 设为 `REQUIRE_USER_INPUT`，并向前端发送 **plan_require_user_input** 事件（带 prompt 文案）。  
- 用户下次在同一 conversation 发消息时，走 **\_handle_conversation_continuation**：  
  - `plan_service.provide_user_response(conversation_id, user_input.query)` 唤醒 Planner 的 `UserInputRequest`，Planner 继续执行直至产出 ExecutionPlan，再执行 plan。

相关类型与事件：

- `SystemResponseEvent.PLAN_REQUIRE_USER_INPUT`、`PlanRequireUserInputResponse`  
- `SystemResponseEvent.PLAN_FAILED`、`PlanFailedResponse`  
- `python/valuecell/core/plan/planner.py`：`UserInputRequest`  
- `python/valuecell/core/plan/service.py`：`UserInputRegistry`  
- `python/valuecell/core/coordinate/orchestrator.py`：`ExecutionContext`、`_monitor_planning_task`、`_handle_conversation_continuation`、`_continue_planning`

---

## 6. 执行计划与单任务执行（Executor）

- **TaskExecutor.execute_plan(plan, thread_id)**  
  - 若有 `plan.guidance_message`，先以 Planner 身份发一条 MESSAGE_CHUNK。  
  - 对 `plan.tasks` 顺序执行：对每个 Task 调用 `execute_task`；若为 SuperAgent 下发的任务（`handoff_from_super_agent`），会先发 subagent conversation START/END 组件、确保子 conversation 存在，再执行。  
- **execute_task**  
  - 更新任务状态、注入 metadata（如 USER_PROFILE、LANGUAGE、TIMEZONE）。  
  - 若是周期任务且未恢复执行，会发 schedule 相关组件并 `done`，然后按 `schedule_config` 循环执行。  
  - 实际单次运行在 **\_execute_single_task_run**：通过 `agent_connections.get_client(agent_name)` 拿到 A2A 客户端，`client.send_message(task.query, ...)`，然后异步消费 `remote_response`，把 `TaskStatusUpdateEvent` 交给 `event_service.route_task_status`，得到消息块、工具调用、**reasoning** 等响应并流出。

即：**任务拆解在 Planner 完成，Executor 只负责按 Task 列表顺序调用远程 Agent 并流式转发事件（含 reasoning）**。

---

## 7. 小结（数据流）

```
用户输入
  → Orchestrator.process_user_input
  → (若未指定 Agent) SuperAgent.run
      → 流式推理字符串 → reasoning_started / reasoning / reasoning_completed
      → SuperAgentOutcome: ANSWER → 直接返回答案
      → SuperAgentOutcome: HANDOFF_TO_PLANNER → enriched_query 进入 Planner
  → PlanService.start_planning_task
      → (passthrough) 单任务 ExecutionPlan
      → (否则) ExecutionPlanner.create_plan
          → agent.run(PlannerInput) → PlannerResponse
          → 校验 adequate / tasks / agent_name → List[Task]
  → TaskExecutor.execute_plan(plan, thread_id)
      → 对每个 task: execute_task → _execute_single_task_run
      → A2A client.send_message → TaskStatusUpdateEvent
      → route_task_status → 消息 / 工具调用 / reasoning 事件 → 前端
```

- **推理**：SuperAgent 与子 Agent 的「思考过程」通过 reasoning 三件套事件流式呈现；Planner 的「推理」体现在 LLM 产出结构化 PlannerResponse（任务拆解与 adequate/guidance）。  
- **任务拆解**：由 Planner 的 LLM + 工具（get_enabled_agents / get_agent_description）在 `_analyze_input_and_create_tasks` 中完成，结果为 `ExecutionPlan.tasks`（List[Task]），当前策略是单任务为主，多任务未展开。  
- **Plan**：即 `ExecutionPlan`，包含元数据、orig_query、tasks、guidance_message；从创建到执行由 PlanService 与 TaskExecutor 协同完成。
