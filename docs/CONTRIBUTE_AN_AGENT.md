# 为 ValueCell 贡献代理

本指南说明如何构建、集成新的代理并贡献到 ValueCell 的多代理金融平台。

## 快速开始 🚀

想快速创建新代理？您可以使用 AI 编程助手（如 GitHub Copilot、Cursor 或其他代理编码器）自动引导您的代理！

只需将此指南分享给您的 AI 助手并询问：

> "请按照此指南创建一个 HelloAgent。"

AI 将阅读本文档并生成所有必要的文件：

- 代理模块（`core.py`、`__main__.py`、`__init__.py`）
- 配置文件（YAML 和 JSON）
- 代理卡片注册（JSON）

这是最快上手并动手学习代理结构的方法！

## 目录

- [架构概述](#架构概述)
- [创建新代理](#创建新代理)
- [添加代理配置](#添加代理配置-必需)
- [运行您的代理](#运行您的代理)
- [在代理中使用模型和工具](#在代理中使用模型和工具)
- [事件系统](#事件系统-合约)
- [启动后端](#启动后端)
- [调试代理行为](#调试代理行为)

## 架构概述

了解系统架构对于构建代理至关重要：

- **API 后端**：`valuecell.server`（FastAPI/uvicorn）。入口：`valuecell.server.main`
- **代理**：位于 `valuecell.agents.<agent_name>` 下，带有 `__main__.py` 用于 `python -m` 执行
- **核心合约**：`valuecell.core.types` 定义响应事件和数据形状
- **流式助手**：`valuecell.core.agent.stream` 用于发出事件

更多详情，请参阅

- [核心架构文档](./CORE_ARCHITECTURE.md)
- [配置指南](./CONFIGURATION_GUIDE.md)
- [主要贡献指南](../.github/CONTRIBUTING.md)。

## 创建新代理

创建新代理涉及三个核心步骤：

1. **实现代理模块** - 创建包含代理逻辑的 Python 模块
2. **添加代理卡片** - 定义代理的元数据
3. **添加代理配置** - 配置模型参数

让我们详细讲解每个步骤。

### 步骤 1：创建代理目录结构

在 `python/valuecell/agents/` 下为新代理创建新目录：

```bash
mkdir -p python/valuecell/agents/hello_agent
touch python/valuecell/agents/hello_agent/__init__.py
touch python/valuecell/agents/hello_agent/__main__.py
touch python/valuecell/agents/hello_agent/core.py
```

### 步骤 2：实现您的代理逻辑

在 `core.py` 中，子类化 `BaseAgent` 并实现 `stream()` 方法：

```python
# file: valuecell/agents/hello_agent/core.py
from typing import AsyncGenerator, Optional, Dict
from valuecell.core.types import BaseAgent, StreamResponse
from valuecell.core.agent import streaming

class HelloAgent(BaseAgent):
   async def stream(
      self,
      query: str,                    # 用户查询内容
      conversation_id: str,          # 对话 ID
      task_id: str,                  # 任务 ID
      dependencies: Optional[Dict] = None,  # 可选上下文（语言、时区等）
   ) -> AsyncGenerator[StreamResponse, None]:
      """
      处理用户查询并返回流式响应。
      
      Args:
          query: 用户查询内容
          conversation_id: 对话的唯一标识符
          task_id: 任务的唯一标识符
          dependencies: 可选依赖项，包含语言、时区和其他上下文
      
      Yields:
          StreamResponse: 包含内容和完成状态的流式响应
      """
      # 发送几个块，然后完成
      yield streaming.message_chunk("思考中…")
      yield streaming.message_chunk(f"您说：{query}")
      yield streaming.done()
```

**代理处理流程要点：**

1. **返回文本内容**：使用 `streaming.message_chunk()` 返回文本响应。您可以发送完整消息或将其拆分为较小的块以获得更好的流式用户体验。
2. **发出完成信号**：始终以 `streaming.done()` 结尾，表示代理已完成处理。

这个简单的流程实现了与 UI 的实时通信，在生成响应时显示响应。

### 步骤 3：添加代理入口点

在 `__main__.py` 中，包装您的代理以进行独立执行。此文件使您能够使用 `uv run -m` 启动代理：

```python
# file: valuecell/agents/hello_agent/__main__.py
import asyncio
from valuecell.core.agent import create_wrapped_agent
from .core import HelloAgent

if __name__ == "__main__":
   agent = create_wrapped_agent(HelloAgent)
   asyncio.run(agent.serve())
```

> [!IMPORTANT]
> 始终将包装和服务逻辑放在 `__main__.py` 中。此模式支持：
>
> - 通过 `uv run -m valuecell.agents.your_agent` 一致地启动代理
> - ValueCell 后端服务器自动发现
> - 标准化传输和事件发出

运行您的代理：

```bash
cd python
uv run -m valuecell.agents.hello_agent
```

> [!TIP]
> 包装器标准化传输和事件发出，使您的代理能够与 UI 和日志一致地集成。

## 添加代理配置（必需）

代理配置定义代理如何使用模型、嵌入和运行时参数。在 `python/configs/agents/` 中创建 YAML 文件。

### 创建配置文件

创建 `python/configs/agents/hello_agent.yaml`：

```yaml
name: "Hello Agent"
enabled: true

# 模型配置
models:
  # 主模型
  primary:
    model_id: "anthropic/claude-haiku-4.5"
    provider: "openrouter"

# 环境变量覆盖
env_overrides:
  HELLO_AGENT_MODEL_ID: "models.primary.model_id"
  HELLO_AGENT_PROVIDER: "models.primary.provider"
```

> [!TIP]
> YAML 文件名应与代理的模块名匹配（例如，`hello_agent.yaml` 对应 `hello_agent` 模块）。此命名约定有助于在整个代码库中保持一致性。
> 有关详细配置选项，包括嵌入模型、回退提供商和高级模式，请参阅 [CONFIGURATION_GUIDE](./CONFIGURATION_GUIDE.md)。

### 在代理中使用配置

使用配置管理器加载代理的配置。传递给 `get_model_for_agent()` 的代理名称必须与 YAML 文件名匹配（不带 `.yaml` 扩展名）：

```python
from valuecell.utils.model import get_model_for_agent

class HelloAgent(BaseAgent):
   def __init__(self, **kwargs):
      super().__init__(**kwargs)
      # 自动从 hello_agent.yaml 加载配置
      # 代理名称 "hello_agent" 必须与 YAML 文件名匹配
      self.model = get_model_for_agent("hello_agent")
   
   async def stream(self, query, conversation_id, task_id, dependencies=None):
      # 使用您配置的模型
      response = await self.model.generate(query)
      yield streaming.message_chunk(response)
      yield streaming.done()
```

### 运行时配置覆盖

您可以通过环境变量覆盖配置：

```bash
# 在运行时覆盖模型
export HELLO_AGENT_MODEL_ID="anthropic/claude-3.5-sonnet"
export HELLO_AGENT_TEMPERATURE="0.9"

# 使用覆盖运行代理
uv run -m valuecell.agents.hello_agent
```

> [!TIP]
> 有关详细配置选项，包括嵌入模型、回退提供商和高级模式，请参阅 [CONFIGURATION_GUIDE](./CONFIGURATION_GUIDE.md)。

## 添加代理卡片

代理卡片声明如何发现和服务您的代理。在以下位置放置 JSON 文件：

`python/configs/agent_cards/`

`name` 必须与您的代理类名匹配（例如，`HelloAgent`）。`url` 决定包装代理将绑定到的主机/端口。

### 最小示例

```json
{
  "name": "HelloAgent",
  "url": "http://localhost:10010",
  "description": "一个回显输入的最小示例代理。",
  "capabilities": { "streaming": true, "push_notifications": false },
  "default_input_modes": ["text"],
  "default_output_modes": ["text"],
  "version": "1.0.0",
  "skills": [
   {
     "id": "echo",
     "name": "Echo",
     "description": "将用户输入作为流式块回显。",
     "tags": ["example", "echo"]
   }
  ]
}
```

> [!TIP]
>
> - 文件名可以是任何内容（例如，`hello_agent.json`），但 `name` 必须等于您的代理类（由 `create_wrapped_agent` 使用）
> - 可选的 `enabled: false` 将禁用加载。额外字段如 `display_name` 或 `metadata` 会被忽略
> - 如果端口被占用，请更改 `url` 端口。包装器在服务时从此 URL 读取主机/端口
> - 如果看到"在代理卡片中未找到代理配置…"，请检查 `name` 和 JSON 位置

## 运行您的代理

### 本地开发

对于本地 Web 开发，只需启动后端服务器，它将自动加载所有代理：

```bash
# 启动完整堆栈（前端 + 后端及所有代理）
bash start.sh

# 或仅启动后端
bash start.sh --no-frontend
```

后端将根据代理卡片配置自动发现并初始化您的代理。

### 直接代理执行

您也可以使用 Python 模块语法直接运行代理：

```bash
cd python
uv run python -m valuecell.agents.hello_agent
```

### 客户端应用程序

对于打包的客户端应用程序（Tauri）：
1. 代理将自动包含在构建中
2. 无需额外注册
3. 使用工作流构建进行测试：`.github/workflows/mac_build.yml`

> [!TIP]
> 环境变量从系统应用程序目录加载：
> - **macOS**：`~/Library/Application Support/ValueCell/.env`
> - **Linux**：`~/.config/valuecell/.env`
> - **Windows**：`%APPDATA%\ValueCell\.env`
> 
> 如果 `.env` 文件不存在，将在首次运行时从 `.env.example` 自动创建。
> 本地开发和打包客户端使用相同的位置。

## 在代理中使用模型和工具

代理可以使用工具来扩展其功能。工具是代理在执行期间可以调用的 Python 函数。

### 定义工具

```python
from agno.agent import Agent
from agno.db.in_memory import InMemoryDb
from valuecell.utils.model import get_model_for_agent

def search_stock_info(ticker: str) -> str:
    """
    按股票代码搜索股票信息。
    
    Args:
        ticker: 股票代码（例如，"AAPL"、"GOOGL"）
    
    Returns:
        股票信息字符串
    """
    # 您的工具实现
    return f"股票信息 {ticker}"

def calculate_metrics(data: dict) -> dict:
    """
    从股票数据计算财务指标。
    
    Args:
        data: 包含财务数据的字典
    
    Returns:
        包含计算指标的字典
    """
    # 您的计算逻辑
    return {"pe_ratio": 25.5, "market_cap": "2.5T"}

class MyAgent(BaseAgent):
   def __init__(self, **kwargs):
      super().__init__(**kwargs)
      self.inner = Agent(
         ...
         tools=[search_stock_info, calculate_metrics],  # 注册您的工具
         ...
      )
```

### 工具最佳实践

- **清晰的文档字符串**：工具应具有描述性文档字符串，说明其目的和参数
- **类型提示**：对所有参数和返回值使用类型提示
- **错误处理**：在工具内实现适当的错误处理
- **专注功能**：每个工具应该做好一件事

> [!TIP]
> 更多信息，请参阅 [Tools - Agno](https://docs.agno.com/concepts/agents/tools)。

## 事件系统（合约）

事件系统实现代理和 UI 之间的实时通信。所有事件都在 `valuecell.core.types` 中定义。

### 流式事件

用于流式代理响应的事件：

- `MESSAGE_CHUNK` - 代理响应消息的一个块
- `TOOL_CALL_STARTED` - 代理开始执行工具
- `TOOL_CALL_COMPLETED` - 工具执行完成
- `COMPONENT_GENERATOR` - 丰富格式组件（图表、表格、报告等）
- `DONE` - 表示流式传输已完成

#### 组件生成器事件

`COMPONENT_GENERATOR` 事件允许代理发送超出纯文本的丰富 UI 组件。这支持交互式可视化、结构化数据显示和自定义小部件。

**支持的组件类型：**

- `report` - 带有格式化内容的研究报告
- `profile` - 公司或股票档案
- `filtered_line_chart` - 带数据过滤的交互式折线图
- `filtered_card_push_notification` - 带过滤选项的通知卡片
- `scheduled_task_controller` - 用于管理计划任务的 UI
- `scheduled_task_result` - 显示计划任务的结果

**示例：发出组件**

```python
from valuecell.core.agent import streaming

# 创建折线图组件
yield streaming.component_generator(
    component_type="filtered_line_chart",
    content={
        "title": "股价趋势",
        "data": [
            ["Date", "AAPL", "GOOGL", "MSFT"],
            ["2025-01-01", 150.5, 2800.3, 380.2],
            ["2025-01-02", 152.1, 2815.7, 382.5],
        ],
        "create_time": "2025-01-15 10:30:00"
    }
)

# 创建报告组件
yield streaming.component_generator(
    component_type="report",
    content={
        "title": "2024 年第四季度财务分析",
        "data": "## 执行摘要\n\n收入增长 15%...",
        "url": "https://example.com/reports/q4-2024",
        "create_time": "2025-01-15 10:30:00"
    }
)
```

> [!TIP]
> 组件数据结构在 `valuecell.core.types` 中定义。请参阅 `ReportComponentData`、`FilteredLineChartComponentData` 和其他组件负载类以了解必需字段。

### 在代理中发出事件

使用 `streaming.*` 助手发出事件。以下是基于 Research Agent 实现的实用示例：

```python
from agno.agent import Agent
from valuecell.core.agent import streaming
from valuecell.utils.model import get_model_for_agent

class MyAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.inner = Agent(
            model=get_model_for_agent("my_agent"),
            tools=[...],  # 您的工具函数
            # ... 其他配置
        )
    
    async def stream(self, query, conversation_id, task_id, dependencies=None):
        # 从内部代理流式传输响应
        response_stream = self.inner.arun(
            query,
            stream=True,
            stream_intermediate_steps=True,
            session_id=conversation_id,
        )
        
        # 处理并转发来自内部代理的事件
        async for event in response_stream:
            if event.event == "RunContent":
                # 在消息块到达时发出
                yield streaming.message_chunk(event.content)
            
            elif event.event == "ToolCallStarted":
                # 通知 UI 正在调用工具
                yield streaming.tool_call_started(
                    event.tool.tool_call_id, 
                    event.tool.tool_name
                )
            
            elif event.event == "ToolCallCompleted":
                # 将工具结果发送回 UI
                yield streaming.tool_call_completed(
                    event.tool.result,
                    event.tool.tool_call_id,
                    event.tool.tool_name
                )
        
        # 发出完成信号
        yield streaming.done()
```

> [!TIP]
> 有关详细信息，请参阅 [Running Agents - Agno](https://docs.agno.com/concepts/agents/running-agents)

> [!TIP]
> UI 会自动适当地渲染不同的事件类型 - 消息作为文本，工具调用带有图标等。请参阅 `python/valuecell/agents/research_agent/core.py` 中的完整 Research Agent 实现。

## 启动后端

### 运行 API 服务器

从 `python/` 文件夹：

```bash
cd python
python -m valuecell.server.main
```

### 运行代理

将 Hello Agent 作为独立服务运行：

```bash
cd python
python -m valuecell.agents.hello_agent
```

> [!TIP]
> 首先设置您的环境。至少配置 `SILICONFLOW_API_KEY`（和 `OPENROUTER_API_KEY`）和 `SEC_EMAIL`。请参阅 [CONFIGURATION_GUIDE](./CONFIGURATION_GUIDE.md)。
> 可选：设置 `AGENT_DEBUG_MODE=true` 以在本地跟踪模型行为。

## 调试代理行为

使用 `AGENT_DEBUG_MODE` 启用来自代理和规划器的详细跟踪：

- 记录提示、工具调用、中间步骤和提供商响应元数据
- 有助于在开发期间调查规划决策和工具路由

在 `.env` 中启用：

```bash
AGENT_DEBUG_MODE=true
```

> [!CAUTION]
> 调试模式可以记录敏感输入/输出并增加日志量/延迟。仅在本地/开发环境中启用；在生产中保持关闭。

## 有问题？

如果您有问题：

- 💬 加入我们的 [Discord](https://discord.com/invite/84Kex3GGAh)
- 📧 发送邮件至 [public@valuecell.ai](mailto:public@valuecell.ai)
- 🐛 为错误报告打开 issue

---

感谢您为 ValueCell 做出贡献！🚀🚀🚀
