\#Drawer Agent说明

本Agent用python写成，通过命令行运行，主要通过接入ai服务的api，对本仓库的文献进行检索与翻译。Drawer Agent支持翻译、分析等多种功能，适合接入复杂ai使用，drawer agent simple则无翻译功能，建议接入小规模ai使用。

因此本处需自行前往ai平台购买token，根据技术文档提供的api接入链接，以及从ai平台中获得的api\_key，填入agent\_config.py配置文件有关变量。也可以使用本地部署的大模型，如通过llama.cpp运行llama-server的api接口（链接，http://127.0.0.1:端口号），一般不需要api\_key，仅需链接即可（本agent（simple）实测在本地部署的qwen3.5 4B 6位模型中表现尚可，可以完成比较简单的检索任务）。

用户也可以自行打开python文件优化代码、prompts，提升运行效率。运行py文件前请确保系统安装python及所需运行库（httpx、bs4）。

除在api\_key固定存储参数外，运行前也可以在命令行：usezaisearch6.py --xxx中根据需要自行调整配置参数，选项如下：

&#x20; -h, --help            帮助

&#x20; --model MODEL         模型名称

&#x20; --api-url API\_URL     API 地址

&#x20; --api-key API\_KEY     API 密钥

&#x20; --max-context-token MAX\_CONTEXT\_TOKEN 模型最大上下文窗口 token 数

&#x20; --max-tokens MAX\_TOKENS 最大输出 token 数

&#x20; --max-hits MAX\_HITS   搜索最大命中数

&#x20; --temperature TEMPERATURE 温度，控制模型输出随机性

&#x20; --top-p TOP\_P         top-p，控制模型关联token输出

&#x20; --max-tool-result-chars MAX\_TOOL\_RESULT\_CHARS  工具结果最大字符数

&#x20; --html-folder HTML\_FOLDER 文献库根目录

&#x20; --output OUTPUT       历史保存目录

&#x20; --tools               启动时开启工具显示

&#x20; --think               启动时开启思考模式

&#x20; --think-type THINK\_TYPE 模型思考模式加载参数

&#x20; --deep-read           启动时开启深度阅读

