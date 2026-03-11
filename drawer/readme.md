\#Drawer Agent说明

本Agent用python写成，通过命令行运行，主要通过接入ai服务的api，对本仓库的文献进行检索与翻译。Drawer Agent支持翻译、分析等多种功能，适合接入复杂ai使用，drawer agent simple则无翻译功能，建议接入小规模ai使用。

因此本处需自行前往ai平台购买token，根据技术文档提供的api接入链接，以及从ai平台中获得的api\_key，填入agent\_config.py文件有关变量。也可以使用本地部署的大模型，如通过llama.cpp运行llama-server的api接口（链接，http://127.0.0.1:端口号），一般不需要api\_key，仅需链接即可（本agent（simple）实测在本地部署的qwen3.5 4B 6位模型中表现尚可，可以完成比较简单的检索任务）。

用户也可以自行打开python文件优化代码、prompts，提升运行效率。运行py文件前请确保系统安装python及所需运行库（httpx、bs4）。

