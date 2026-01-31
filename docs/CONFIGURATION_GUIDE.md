# 配置指南

ValueCell 项目使用**三层配置系统**，支持从开发到生产的灵活部署。本指南涵盖配置代理、提供商和模型的所有方面。

## 配置优先级

ValueCell 按以下顺序（从高到低）解析多个配置源：

1. **环境变量** - 运行时覆盖（例如，`OPENROUTER_API_KEY`）
2. **.env 文件** - 用户级配置（在项目根目录）
3. **YAML 文件** - 系统默认值（在 `python/configs/` 中）

此层次结构允许您：
- 通过 `.env` 设置提供商凭证，无需修改代码
- 通过环境变量在运行时覆盖设置
- 在 YAML 文件中维护合理的默认值

## 快速开始

### 步骤 1：获取 API 密钥

ValueCell 支持多个 LLM 提供商。至少选择一个：

| 提供商        | 注册地址                                             |
| --------------- | --------------------------------------------------- |
| **OpenRouter**  | [openrouter.ai](https://openrouter.ai/)             |
| **SiliconFlow** | [siliconflow.cn](https://www.siliconflow.cn/)       |
| **Google**      | [ai.google.dev](https://ai.google.dev/)             |
| **OpenAI**      | [platform.openai.com](https://platform.openai.com/) |
| **DashScope**   | [bailian.console.aliyun.com](https://bailian.console.aliyun.com/#/home) |

### 步骤 2：配置 .env 文件

复制示例文件并添加您的 API 密钥：
编辑 `.env` 并添加您的凭证：

```bash
# 在项目根目录
cp .env.example .env

# 或使用 SiliconFlow（最适合中文模型和成本）
# 编辑 `.env` 并添加您的凭证：
SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxx

# 或使用 Google Gemini
GOOGLE_API_KEY=AIzaSyDxxxxxxxxxxxxx

# 可选：设置主提供商（如果未设置则自动检测）
PRIMARY_PROVIDER=openrouter
```

### 步骤 3：启动应用程序

```bash
# macOS / Linux
bash start.sh

# Windows PowerShell
.\start.ps1
```

系统将根据配置的 API 密钥自动检测可用的提供商。

> **注意**：如果遇到数据库兼容性错误，请删除以下位置：
> - LanceDB 目录（系统应用程序目录，与 `.env` 相同）：
>   - macOS: `~/Library/Application Support/ValueCell/lancedb`
>   - Linux: `~/.config/valuecell/lancedb`
>   - Windows: `%APPDATA%\\ValueCell\\lancedb`
> - 知识库目录（系统应用程序目录，与 `.env` 相同）：
>   - macOS: `~/Library/Application Support/ValueCell/.knowledge`
>   - Linux: `~/.config/valuecell/.knowledge`
>   - Windows: `%APPDATA%\\ValueCell\\.knowledge`
> - SQLite 数据库文件（系统应用程序目录，与 `.env` 相同）：
>   - macOS: `~/Library/Application Support/ValueCell/valuecell.db`
>   - Linux: `~/.config/valuecell/valuecell.db`
>   - Windows: `%APPDATA%\\ValueCell\\valuecell.db`

---

## 配置系统架构

### 文件结构

```
python/
├── configs/
│   ├── config.yaml                    # 主配置文件
│   ├── config.{environment}.yaml      # 环境特定覆盖
│   ├── providers/
│   │   ├── openrouter.yaml           # OpenRouter 提供商配置
│   │   ├── siliconflow.yaml          # SiliconFlow 提供商配置
│   │   ├── dashscope.yaml            # DashScope（阿里云）提供商配置
│   │   └── other_provider.yaml
│   ├── agents/
│   │   ├── super_agent.yaml          # Super Agent 配置
│   │   ├── research_agent.yaml       # Research Agent 配置
│   │   └── auto_trading_agent.yaml   # Auto Trading Agent 配置
│   ├── agent_cards/                  # 代理的 UI 元数据
│   └── locales/                      # 国际化文件
└── valuecell/
    └── config/
        ├── constants.py              # 配置常量
        ├── loader.py                 # 带环境变量解析的 YAML 加载器
        └── manager.py                # 高级配置 API
```

### 配置解析工作原理

#### 1. 提供商配置加载

当系统需要模型时，它会：

1. **加载提供商 YAML**（例如，`configs/providers/openrouter.yaml`）
2. **解析 `${VAR}` 占位符**，使用环境变量替换 YAML 中的占位符
3. **应用环境变量覆盖**（例如，`OPENROUTER_API_KEY` 覆盖 `connection.api_key`）
4. **返回 ProviderConfig** 对象，包含解析后的值

**示例：OpenRouter 配置**

```yaml
connection:
  base_url: "https://openrouter.ai/api/v1"
  api_key_env: "OPENROUTER_API_KEY"    # 指定要使用的环境变量

default_model: "anthropic/claude-haiku-4.5"

defaults:
  temperature: 0.5
  max_tokens: 4096
```

系统会自动从 `.env` 或环境中读取 `OPENROUTER_API_KEY`。

#### 2. 代理配置加载

当您创建代理（例如，`research_agent`）时，系统会：

1. **加载代理 YAML**（例如，`configs/agents/research_agent.yaml`）
2. 系统会自动从 `.env` 或环境中读取 `OPENROUTER_API_KEY`。
3. **通过 `env_overrides` 映射应用环境变量覆盖**
4. **与 `config.yaml` 中的全局默认值合并**
5. **返回 AgentConfig** 对象，包含完整配置

**示例：代理配置**

```yaml
name: "Research Agent"
enabled: true

models:
  primary:
    model_id: "google/gemini-2.5-flash"
    provider: "openrouter"
    provider_models:
      siliconflow: "Qwen/Qwen3-235B-A22B-Thinking-2507"
      google: "gemini-2.5-flash"
    parameters:
      temperature: 0.7

env_overrides:
  RESEARCH_AGENT_MODEL_ID: "models.primary.model_id"
  RESEARCH_AGENT_PROVIDER: "models.primary.provider"
```

这允许运行时覆盖：

```bash
export RESEARCH_AGENT_MODEL_ID="anthropic/claude-3.5-sonnet"
export RESEARCH_AGENT_PROVIDER="openrouter"
# 现在 research agent 使用 Claude 3.5 Sonnet 而不是 Gemini
```

---

## 详细配置参考

### 全局配置（`config.yaml`）

主配置文件设置系统范围的默认值：

```yaml
models:
  # 如果多个提供商都有 API 密钥，则使用的主提供商
  primary_provider: "openrouter"
  
  # 全局默认参数（除非被覆盖，否则所有模型都使用）
  defaults:
    temperature: 0.5
    max_tokens: 4096
  
  # 提供商注册表
  providers:
    openrouter:
      config_file: "providers/openrouter.yaml"
      api_key_env: "OPENROUTER_API_KEY"
    siliconflow:
      config_file: "providers/siliconflow.yaml"
      api_key_env: "SILICONFLOW_API_KEY"
    google:
      config_file: "providers/google.yaml"
      api_key_env: "GOOGLE_API_KEY"
    dashscope:
      config_file: "providers/dashscope.yaml"
      api_key_env: "DASHSCOPE_API_KEY"

# 代理注册表
agents:
  super_agent:
    config_file: "agents/super_agent.yaml"
  research_agent:
    config_file: "agents/research_agent.yaml"
  auto_trading_agent:
    config_file: "agents/auto_trading_agent.yaml"
```

### 提供商配置

每个提供商在 `configs/providers/` 中都有自己的 YAML 文件。结构如下：

```yaml
name: "Provider Display Name"
provider_type: "provider_id"           # 内部使用
enabled: true                          # 可以在不删除配置的情况下禁用

# 连接详情
connection:
  base_url: "https://api.example.com/v1"
  api_key_env: "PROVIDER_API_KEY"      # 要读取的环境变量
  endpoint_env: "PROVIDER_ENDPOINT"    # 可选：用于 Azure 风格的端点

# 未指定时的默认模型
default_model: "model-id"

# 此提供商所有模型的默认参数
defaults:
  temperature: 0.7
  max_tokens: 4096
  top_p: 0.95

# 可用模型列表
models:
  - id: "model-id-1"
    name: "Model Display Name"
    context_length: 128000
    max_output_tokens: 8192
  
  - id: "model-id-2"
    name: "Another Model"
    context_length: 256000

# 嵌入配置（可选，并非所有提供商都支持）
embedding:
  default_model: "embedding-model-id"
  
  defaults:
    dimensions: 1536
    encoding_format: "float"
  
  models:
    - id: "embedding-model-id"
      name: "Embedding Model"
      dimensions: 1536
      max_input: 8192

# 提供商特定配置
extra_headers:
  HTTP-Referer: "https://valuecell.ai"
  X-Title: "ValueCell"
```

### 代理配置

代理 YAML 文件定义如何初始化代理。主要特性：

```yaml
name: "Agent Display Name"
enabled: true

# 模型配置
models:
  # 主要推理模型
  primary:
    model_id: "model-id"               # 可以使用提供商前缀（例如，"anthropic/claude-3.5-sonnet"）
    provider: "openrouter"             # 必须明确指定（不自动检测）
    
    # 不同提供商的备用模型
    provider_models:
      siliconflow: "qwen/qwen3-max"
      google: "gemini-2.5-flash"
    
    # 模型特定参数（覆盖提供商默认值）
    parameters:
      temperature: 0.8
      max_tokens: 8192
  
  # 可选：单独的嵌入模型配置
  embedding:
    model_id: "embedding-model-id"
    provider: "siliconflow"
    provider_models:
      google: "gemini-embedding-001"
    parameters:
      dimensions: 2560

# 将环境变量映射到配置路径以进行运行时覆盖
env_overrides:
  # 语法：ENV_VAR -> config.path.to.value
  AGENT_MODEL_ID: "models.primary.model_id"
  AGENT_PROVIDER: "models.primary.provider"
  AGENT_TEMPERATURE: "models.primary.parameters.temperature"
  AGENT_MAX_TOKENS: "models.primary.parameters.max_tokens"
  
  # 嵌入配置
  AGENT_EMBEDDER_MODEL: "models.embedding.model_id"
  AGENT_EMBEDDER_PROVIDER: "models.embedding.provider"

```

---

## 提供商自动检测和回退

### 自动检测

ValueCell 根据可用的 API 密钥自动选择主提供商：

**优先级顺序**（如果多个提供商都有 API 密钥）：

选择逻辑在 `python/valuecell/config/manager.py` 中实现：

1. OpenRouter
2. SiliconFlow
3. Google
4. OpenAI
5. OpenAI-Compatible
6. Azure
7. 其他配置的提供商（包括 DashScope、DeepSeek 等）

通过环境变量覆盖：

```bash
export PRIMARY_PROVIDER=siliconflow
```

或禁用自动检测：

```bash
export AUTO_DETECT_PROVIDER=false
```

### 回退机制

如果主提供商失败，ValueCell 会自动尝试回退提供商。

**回退链**（从启用的提供商自动填充）：
- 除主提供商外，所有具有有效 API 密钥的提供商
- 在第一次成功的模型创建时停止

覆盖回退提供商：

```bash
export FALLBACK_PROVIDERS=siliconflow,google
```

禁用回退：

```bash
# 在代理 YAML 中
use_fallback: false
```

### 提供商特定模型映射

使用回退时，代理可以为每个提供商指定要使用的模型：

```yaml
# 在代理配置中
models:
  primary:
    model_id: "anthropic/claude-haiku-4.5"
    provider: "openrouter"
    
    # 如果 OpenRouter 失败，为回退提供商使用这些模型
    provider_models:
      siliconflow: "zai-org/GLM-4.6"      # 类似能力
      google: "gemini-2.5-flash"          # 快速高效
```

当发生回退时：
1. 尝试使用 `anthropic/claude-haiku-4.5` 的 OpenRouter
2. 如果失败，尝试使用 `zai-org/GLM-4.6` 的 SiliconFlow
3. 如果失败，尝试使用 `gemini-2.5-flash` 的 Google

---

## 环境变量参考

### 全局配置

```bash
# 主提供商选择
PRIMARY_PROVIDER=openrouter

# 从 API 密钥自动检测提供商（默认：true）
AUTO_DETECT_PROVIDER=true

# 逗号分隔的回退提供商链
FALLBACK_PROVIDERS=siliconflow,google

# 应用程序环境
APP_ENVIRONMENT=production
```

### 提供商凭证

```bash
# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx

# SiliconFlow
SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxx

# Google
GOOGLE_API_KEY=AIzaSyDxxxxxxxxxxxxx

# Azure OpenAI（如果使用 Azure 提供商）
AZURE_OPENAI_API_KEY=xxxxxxxxxxxxx
AZURE_OPENAI_ENDPOINT=https://xxxxx.openai.azure.com/
OPENAI_API_VERSION=2024-10-21

# DashScope（阿里云 Qwen3 模型）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxx
```

### 模型配置

```bash
# 全局模型覆盖
PLANNER_MODEL_ID=anthropic/claude-3.5-sonnet
EMBEDDER_MODEL_ID=openai/text-embedding-3-large

# Research Agent
RESEARCH_AGENT_MODEL_ID=google/gemini-2.5-flash
RESEARCH_AGENT_PROVIDER=openrouter
RESEARCH_AGENT_TEMPERATURE=0.8
RESEARCH_AGENT_MAX_TOKENS=8192
EMBEDDER_DIMENSION=3072

# Super Agent
SUPER_AGENT_MODEL_ID=anthropic/claude-haiku-4.5
SUPER_AGENT_PROVIDER=openrouter

# Auto Trading Agent
AUTO_TRADING_AGENT_MODEL_ID=model-id
AUTO_TRADING_AGENT_PROVIDER=openrouter
```

### 调试

```bash
# 启用调试日志
AGENT_DEBUG_MODE=true
```

---

## 配置模式

### 模式 1：带回退的多模型设置

**用例**：高可用性和成本优化

```bash
# .env 文件
OPENROUTER_API_KEY=sk-or-v1-xxxxx        # 主：访问许多模型
SILICONFLOW_API_KEY=sk-xxxxx             # 回退：成本效益高
GOOGLE_API_KEY=AIzaSyD-xxxxx             # 第二回退：专业化
DASHSCOPE_API_KEY=sk-xxxxx               # DashScope：Qwen3 模型（中文优化）

# config.yaml
models:
  primary_provider: "openrouter"          # 主（最佳模型）
  # 回退自动填充为 [siliconflow, google]
```

### 模式 2：每个代理的专用模型

**用例**：为每个代理优化其任务

```yaml
# 在 research_agent.yaml 中
models:
  primary:
    provider: "openrouter"
    model_id: "anthropic/claude-3.5-sonnet"  # 最适合研究
    
  embedding:
    provider: "siliconflow"
    model_id: "Qwen/Qwen3-Embedding-4B"      # 最佳嵌入
```

### 模式 3：开发与生产

### OKX 交易

| 变量                 | 默认值 | 描述                                                        |
| ------------------------ | ------- | ------------------------------------------------------------------ |
| `OKX_NETWORK`            | `paper` | 选择 `paper` 进行模拟交易或 `mainnet` 进行实盘环境。 |
| `OKX_API_KEY`            | —       | 从 OKX 控制台生成的 OKX API 密钥。                        |
| `OKX_API_SECRET`         | —       | 与密钥对应的 API 密钥。                               |
| `OKX_API_PASSPHRASE`     | —       | 创建 OKX API 密钥时设置的密码。                      |
| `OKX_ALLOW_LIVE_TRADING` | `false` | 在将订单路由到主网环境之前必须为 `true`。   |
| `OKX_MARGIN_MODE`        | `cash`  | 传递给 OKX 的交易模式（`cash`、`cross`、`isolated`）。          |
| `OKX_USE_SERVER_TIME`    | `false` | 启用以与 OKX 服务器时间同步以进行订单时间戳。            |

> [!IMPORTANT]
> 在 OKX 模拟环境中验证策略之前，保持 `OKX_ALLOW_LIVE_TRADING=false`。将 API 密钥视为生产凭证，并将其存储在安全的保险库中。

## 故障排除

```bash
# .env.production  
OPENROUTER_API_KEY=sk-or-v1-prod-xxxxx
SILICONFLOW_API_KEY=sk-prod-xxxxx
APP_ENVIRONMENT=production
```

然后创建 `config.production.yaml`，包含生产特定设置。

### 模式 4：运行时覆盖

**用例**：在不更改代码的情况下 A/B 测试不同模型

```bash
# 测试不同模型的脚本
for model in "gpt-4o" "claude-3.5-sonnet" "gemini-2.5-flash"; do
    echo "Testing: $model"
    RESEARCH_AGENT_MODEL_ID="$model" python your_script.py
done
```

---

## 开发者指南

### 配置系统架构

配置系统有三层：

1. **加载器层**（`valuecell/config/loader.py`）
   - 读取 YAML 文件
   - 解析 `${VAR}` 占位符
   - 应用环境变量覆盖
   - 实现缓存

2. **管理器层**（`valuecell/config/manager.py`）
   - 高级配置访问
   - 提供商验证
   - 模型工厂集成
   - 回退链管理

3. **工厂层**（`valuecell/adapters/models/factory.py`）
   - 创建实际模型实例
   - 提供商特定实现
   - 参数合并
   - 错误处理和回退


### 创建模型

```python
from valuecell.utils.model import get_model, get_model_for_agent

# 使用默认配置
model = get_model("PLANNER_MODEL_ID")

# 使用 kwargs 覆盖
model = get_model("RESEARCH_AGENT_MODEL_ID", temperature=0.9, max_tokens=16384)

# 获取代理特定模型
model = get_model_for_agent("research_agent", temperature=0.8)

# 使用特定提供商
from valuecell.utils.model import create_model_with_provider
model = create_model_with_provider("openrouter", "anthropic/claude-3.5-sonnet")
```

### 添加新提供商

1. **创建提供商 YAML**（`configs/providers/my_provider.yaml`）
2. **在 `valuecell/adapters/models/factory.py` 中实现提供商类**
3. **在 `ModelFactory._providers` 中注册提供商**
4. **添加到 config.yaml** 提供商注册表
5. **添加提供商配置测试**

---

## 最佳实践

1. **在 .env 中设置 API 密钥**
   - 永远不要将 API 密钥提交到版本控制
   - 使用 `.gitignore` 排除 `.env`
   - 在 CI/CD 中使用环境变量

2. **使用提供商回退**
   - 配置多个提供商以提高可靠性
   - 在代理中指定 `provider_models` 以保持一致的回退
   - 在部署前测试回退行为

3. **监控配置**
   - 记录配置选择决策
   - 在启动时验证配置
   - 在生产中提醒缺少 API 密钥

4. **版本化配置**
   - 在版本控制中保留代理配置
   - 记录选择特定模型的原因
   - 在代码审查中审查配置更改

5. **优化成本**
   - 对简单任务使用更便宜的模型
   - 对实时应用程序使用更快的模型
   - 监控 API 使用情况并设置支出限制

---

## 支持

如有配置问题或疑问：
- 在 [Discord 社区](https://discord.com/invite/84Kex3GGAh) 提问
- 在 [GitHub Issues](https://github.com/valuecell/valuecell/issues) 报告错误
