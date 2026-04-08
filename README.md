# Smart Insole Collector

智能鞋垫实时采集与压力标定桌面工具（PySide6 + pyqtgraph）。

## 功能概览

- 串口高速采集：`921600 / 8N1`，支持断线检测与自动重连尝试
- 协议解析：帧头同步、双子包合并、错误计数
- 实时可视化：热力图、时序曲线、分区指标、IMU 姿态
- 标定流程：分区零点校准、多点采集、线性拟合、JSON 导入导出
- 数据录制：CSV 异步写盘，避免阻塞采集链路

## 运行环境

- Python 3.11+
- Windows 10/11（当前主要验证平台）

## 安装与启动

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 目录结构

```text
smart_insole/
├── main.py
├── config.py
├── communication/
├── data/
├── ui/
├── utils/
├── tests/
├── docs/
└── calibration_files/
```

## 常见问题与异常恢复

- 串口连接失败：确认端口未被占用，点击“刷新”后重连
- 运行中断开：系统会进入异常状态并持续尝试重连，`reconnect_count` 会增加
- 程序异常退出：查看 `logs/app.log` 与 `logs/comm.log`

## 文档

- 设计文档：`docs/设计文档.md`
- Git 提交规范：`docs/Git提交规范.md`

