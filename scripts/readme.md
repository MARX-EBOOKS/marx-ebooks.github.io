# Drawer Agent说明

本Agent用python写成，通过命令行运行，主要通过接入ai服务的api，对本仓库的文献进行检索与翻译。Drawer Agent支持翻译、分析等多种功能，适合接入复杂ai使用，drawer agent simple则无翻译功能，建议接入小规模ai使用。

因此本处需自行前往ai平台购买token，根据技术文档提供的api接入链接，以及从ai平台中获得的api_key，填入agent_config.py配置文件有关变量。也可以使用本地部署的大模型，如通过llama.cpp运行llama-server的api接口（链接，http://127.0.0.1:端口号），一般不需要api_key，仅需链接即可（本agent（simple）实测在本地部署的qwen3.5 4B 6位模型中表现尚可，可以完成比较简单的检索任务）。

用户也可以自行打开python文件优化代码、prompts，提升运行效率。运行py文件前请确保系统安装python及所需运行库（httpx、bs4）。

除在api_key固定存储参数外，运行前也可以在命令行：drawer_agent.py --xxx中根据需要自行调整配置参数，选项如下：

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

# 照排 agent 工作流说明

主要由以下几个脚本构成：
- PDF 解包脚本 unpackpdf.py，图片查阅脚本 usepic.py，图片打开 agent useaipdf2pa.py
- 篇目页码数组和目录内容存储脚本 MEWbrief.py / MEGAok.py 等
- 照排 agent useaipdf3.py（同 LLM 对话，LLM 代发请求）/ useaipdf2.py（同 VLM 对话，直接由 VLM 处理）
- HTML 合并脚本 mewmergebygroup.py / MegaEtxMerger.py 等。
- 最简 HTML 生成管线 MEWmede.py 等，以及独立正则处理脚本 MEW-o1.py 等。

## 主要步骤（以 Marx-Engels-Werke 的某一卷为例）：

- 1. 首先用 unpackpdf.py 把 PDF 解包成图片，unpackpdf.py 在解包后将以标签层页码命名各图片。因此务必预先对 PDF 中的页面标签（输入后可直接跳转的页码，可以通过 Adobe Acrobat PDF 页面缩略图点选页面后，打开右键菜单中的页面标签选项进行编辑）进行预处理，使该页码标签同实际各页面页码保持一致，方便后续处理。
- 2. 根据目录页抓取出各篇目首页页码后，将之存入各卷的 pagenum 中（如 MEWbrief1 / MEWbrief 所示），再调用 search_page_group 生成各篇目的页码组。
  - 分成 MEWbrief1 / MEWbrief 两个脚本，主要是为了更好解决单页转换和跨页注释的问题，因此即便在逐页转换的情况下（如 MEWbrief.py 的页码组划分），也得预先标记出跨页注释所在的页码，保证他们预先分到一个页码组内，以便后续检查。
  - 同时 agent 批量转换管线和合并管线的信息要求也不尽相同，有的信息只有 agent 管线需要，而有的信息是合并管线必备的，信息的颗粒度也不一样，塞到一个文件里也不便于管理。
- 3. 使用 usepic.py 或 useaipdf2pa.py 打开对应卷的 pdf 页面，标记无法被程序机械拼接的跨页段落：跨页段落的右下边缘处如果有句号、感叹号、问号、括号、脚注等无法用正则表达式处理的文本，或者换另一种说法，只要跨页段落的右下边缘处不是逗号、连字符、单词，就记录在各卷的 mergepa 中，以供之后的合并脚本标记、拼接。
  - 卷号参数在脚本名后加 -v 输入。如 python useaipdf2pa.py -v 23，usepic.py -v 23 -p 46 47 48 等。
  - usepic.py 支持两种输入模式：在 -p 后加页码打开对应页码的页面，在 -b 后加页码或范围打开对应的页面。
  - useaipdf2pa.py 可以利用命令行中暂存的命令反复批量打开。
  - 因 AI 目前并不能准确识别段前缩进，并不能分辨那些地方是刚好段落结束、那些地方则是跨页段落。而正则表达式更无法区分句号、感叹号、问号、括号、脚注等内容是接在跨页段落后还是接在普通段落后。如果不做标记，要么只能一刀切的对所有跨页内容无条件合并，要么就会把跨页段落给分成两段破坏语义。因此在目前技术条件下，针对跨页段落的情况，只能依靠人工进行标记。
  - 但一般来说，从 MEWbrief1.py 的 mergepa 中可以看到，一卷内这种无法被机械拼接的跨页段落往往也是极其有限的。所以哪怕 AI 具备准确识别段前缩进的能力，效费也不成正比。总归，人工是处理该情况的最优解。
  - 关于跨页段落拼接的情况，可以参考 mewmergebygroup.py 的 merge_group 函数中给页码标签加 mergepa 类，以及后续 _build_process_full_html 中与 mergepa 类相关的各个正则表达式：主要的操作也很简单粗暴，就是特定字段做标记然后再删掉。
- 4. 使用 useaipdf3.py / useaipdf2.py 进行转换。useaipdf3.py 设计为 LLM 代发请求给 VLM，适合用于批量转换。 useaipdf2.py 设计为 VLM 接收用户请求后直接进行操作，适合单个篇目 / 页码组的转换，或转换后批量进行校对、检查等工作。
  - Agent 运行的核心代码在 VLMClient, Agent 和 AppController 几个类中。VLMClient 负责请求与接收，Agent 负责跑聊天循环，AppController 负责接收命令行输入。目前对并发的管理较为薄弱，可以考虑进一步改进。
  - ToolHandler 中为下发给 Agent 的各个工具，如过于影响代码维护，可以考虑将工具的解释文本单独存放在 json 文件中。如果需要其他特定功能，可以在工具映射表 ALL_TOOLS 和函数和工具名映射表 self._dispatch 中自行添加工具供 AI 使用。
  - Agent 的 system prompts 通过 get_system_prompt 定义，此处同时将前期标注的页码组 / 篇目组输入给 Agent 供其发送请求、转换。
- 5. 转换后打开拼接脚本，如 mewmergebygroup.py 进行拼接。在 main 中也可以指定要拼接的 volumes 单独拼接。
  - 如有多页组，在拼接之前应先插入对应页码锚点。这对拼接无作用，但影响后续 JS 对页码锚点的读取。
  - 在插入页码锚点的过程中也可以同时检查多页转换的正误、缺漏，如有错漏也可重新转换。
- 6. 拼接后打开最终 HTML 和数据生成器脚本 MEWmede.py 生成 HTML 目录。MEW-o1.py 是为了对 MLwerke.de 中的 90 年代网页进行大量繁杂的正则处理而从 MEWmede.py 中剥离的 HTML 生成器的入口，目前仍负责对各路 HTML，包括 AI 生成的 HTML 进行最终的正则处理。
  - 可以根据最终生成的目录页判断 AI 转换的标题层级是否正确，如不正确，可以手动修改标题层级后，再进行拼接、重新转换。
# 阅读器 JS 应用说明
主要分两个方向：
1. SPA：docs/reader.html 及 docs/reader-nav.js, docs/reader-ui.js, docs/reader-pagebar.js, docs/reader-nav.js。
2. SSG: 根目录的 build11.js, nav.js, reader.js。

两者均通过 libmap.js 渲染菜单路径及引用内容。
- 如果要加入卷册，注意 libmap 中的 dir 属性应按照对应站点根目录计算的绝对路径（以 / 开头供浏览器打开）赋值，以供 nav.js 和构建脚本正确处理。
- 同时，libmap 中的 basePath 也应该以libmap所在目录为基准计算相对路径，以供 reader-nav.js正确拼接 。
- 虽然支持自定义主页（homePage 属性），但仍建议各卷目录页以 index.html 命名，以供一般服务器正确路由。
- 如需引用信息功能，可以在 libmap.js 各全集、各组、各卷的 citation 中为 reader-pagebar.js 中录入引用信息前缀： prefix 为全集或书籍的固定信息, year 为出版年份, publisher 为出版社。暂仅支持德语 S 开头的页码锚点<a id="Sxxx"></a>。
- 目前仅 SPA 支持页码信息引用，SSG 为保持纯净文档站架构，暂不计划支持。