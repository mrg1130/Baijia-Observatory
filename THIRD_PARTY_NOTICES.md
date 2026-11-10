# 上游与第三方说明 / Upstream and third-party notices

## 本项目新增部分 / Original project contributions

Copyright (c) 2026 mrg1130.

本项目新增的桌面工作台、采集适配、统计器、测试、安装脚本、图标和文档采用根目录 [LICENSE](LICENSE) 中的 MIT 条款。MIT 授权范围为本项目的新增原创部分。

The original desktop workspace, collector adapters, calculators, tests, installer scripts, icons and documentation added by this project are covered by the MIT terms in [LICENSE](LICENSE). The MIT grant covers this project's original contributions.

## 上游基础项目 / Upstream baseline

| 项目 / Item | 记录 / Record |
| --- | --- |
| 项目 / Project | [cv-cat/BaijiaApis](https://github.com/cv-cat/BaijiaApis) |
| 检出版本 / Baseline commit | [`2c3d55253fe2c4ea3811bb95a9bcbaf64cd1c165`](https://github.com/cv-cat/BaijiaApis/tree/2c3d55253fe2c4ea3811bb95a9bcbaf64cd1c165) |
| 作者 / Author | cv-cat and upstream contributors |
| 继承文件 / Inherited paths | `baidu_apis.py`, `utils/baidu_utils.py`, `utils/__init__.py`, `requirements.txt` and the upstream portion of `.gitignore` |
| 本地修改 / Local modification | `utils/baidu_utils.py`: Cookie parsing accepts optional whitespace and retains `=` characters within values |
| 许可材料 / Licensing material | 该检出版本未包含独立 LICENSE；其 README 写明学习与技术研究用途。The baseline has no standalone LICENSE file; its README states learning and technical research use. |

继承文件中的原始内容保留上游作者的权利与已有条款。本项目的 MIT 授权不重新许可上游内容。上游的许可材料以[该版本的原始 README](https://github.com/cv-cat/BaijiaApis/blob/2c3d55253fe2c4ea3811bb95a9bcbaf64cd1c165/README.md)和后续获得的授权为准。

Original material in inherited files retains the upstream authors' rights and existing terms. This project's MIT grant does not relicense that material. Refer to the [baseline README](https://github.com/cv-cat/BaijiaApis/blob/2c3d55253fe2c4ea3811bb95a9bcbaf64cd1c165/README.md) and any subsequently obtained permission for upstream licensing material.

## 运行与构建依赖 / Runtime and build dependencies

Python、pywebview、FastAPI、Uvicorn、curl_cffi、Beautiful Soup、websocket-client、HTTPX、keyring、PyInstaller 及其传递依赖，分别适用各自分发包内的许可证。Microsoft WebView2 适用 Microsoft 的运行组件条款；macOS 的系统组件适用相应系统条款。

Python, pywebview, FastAPI, Uvicorn, curl_cffi, Beautiful Soup, websocket-client, HTTPX, keyring, PyInstaller and their transitive dependencies are governed by the licenses supplied with their respective distributions. Microsoft WebView2 is governed by Microsoft's runtime terms, and macOS system components by the corresponding system terms.

具体依赖与版本见 [requirements-studio.txt](requirements-studio.txt)、[requirements-desktop.txt](requirements-desktop.txt) 和 [requirements-build.txt](requirements-build.txt)。本项目新增的 MIT 声明不替代这些依赖的许可证。

See [requirements-studio.txt](requirements-studio.txt), [requirements-desktop.txt](requirements-desktop.txt) and [requirements-build.txt](requirements-build.txt) for direct dependencies and pinned versions. This project's MIT notice does not replace dependency licenses.
