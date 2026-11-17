# 采集说明

## 支持通道

| 通道 | 方式 | 状态 |
|---|---|---|
| 通用 Markdown / TXT | 文件上传或粘贴文本 | P0 已实现 |
| DeepSeek 官方 ZIP | 上传 ZIP，自动识别 JSON/MD/TXT | P0 已实现 |
| 分享链接 | 需要页面正文才能解析 | P1 未实现 |
| Cookie / 登录态抓取 | 合规红线 | 不做 |

## Markdown 角色识别

优先级：

1. 标题式：`### **You**` / `### **Assistant**` / `## 用户` / `## 助手`
2. 行内式：`用户：` / `助手：` / `You:` / `Assistant:`
3. 兜底：整段文本作为单个低置信用户消息，不做角色猜测

`Thinking` / `思考` / `Reasoning` 章节会被排除，不进入助手正文。

## DeepSeek ZIP

采集器会遍历 ZIP 内所有 `.json`、`.md`、`.txt`：

- JSON 中递归查找 `messages` / `conversation` / `chat` 列表
- 角色字段支持 `role` / `author` / `sender` / `from`
- 内容字段支持 `content` / `text` / `message` / `value`
- 时间戳支持 ISO 字符串与 Unix 秒/毫秒
- 无法识别的 ZIP 会退化为 Markdown 解析

由于本地没有真实 ZIP 样本，当前只通过合成 ZIP fixture 做快照测试；正式覆盖率需要补真实导出样本。

## 脱敏规则

采集前必须替换：

- 人名、公司名、项目代号
- 内网地址、本机绝对路径
- API Key、Token、Cookie
- 手机号、邮箱等个人标识

脱敏后的样本只用于本地回归测试，不应包含真实可识别对话内容。

## 预览与纠错

`POST /api/v1/ingestion/preview` 返回：

- 识别标题与时间
- 轮次数
- 每轮用户/助手内容
- 角色置信度
- 异常列表

确认后 `POST /api/v1/ingestion/commit` 写入不可变原始层；纠错记录保存在轮次上。
