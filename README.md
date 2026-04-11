# Smart Insole Collector

智能鞋垫实时数据采集与压力标定桌面工具

基于 **PySide6 + pyqtgraph** 构建，支持 200Hz 高速串口采集、实时热力图可视化、分区压力标定与 CSV 录制，适用于 128 通道压力传感器阵列 + IMU 的智能鞋垫产品。

---

## 功能概览

| 模块 | 功能 |
|------|------|
| 串口管理 | 自动扫描端口、连接/断开、断线自动重连检测 |
| 协议解析 | 帧头同步、双子包合并、丢包/错包统计 |
| 实时热力图 | 128 通道 ADC → 8×16 彩色热力图，RBF 插值平滑，支持 jet/viridis/inferno 色图切换 |
| 关键指标面板 | 实时总压力、压力重心（CoP）、峰值压力、帧率（FPS） |
| 时序曲线 | 任意通道或区域均值的滚动压力-时间曲线 |
| IMU 姿态 | 四元数显示 + 欧拉角（Roll/Pitch/Yaw）转换 |
| 压力标定 | 5 步向导：掩码检测 → 零点校准 → 多点采集 → 分区线性拟合 → JSON 导出/导入 |
| 数据录制 | 异步 CSV 写盘，不阻塞采集链路 |
| ADC/kPa 切换 | 热力图与时序曲线支持「原始 ADC / 标定后 kPa」两种显示模式 |

---

## 运行环境

- **Python**：3.11 或更高
- **操作系统**：Windows 10/11（主要验证平台）；macOS / Linux 理论可用，未全面测试
- **硬件**：带 USB 串口的智能鞋垫（921600 baud，8N1），或无硬件时可直接运行查看 UI

---

## 安装步骤

```bash
# 1. 克隆仓库
git clone <repo_url>
cd smart_insole

# 2. 创建虚拟环境
python -m venv .venv

# 3. 激活虚拟环境
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 4. 安装依赖
pip install -r requirements.txt
```

**依赖清单**（`requirements.txt`）：

| 包 | 版本 | 用途 |
|----|------|------|
| PySide6 | 6.8.1 | Qt6 GUI 框架 |
| pyqtgraph | 0.13.7 | 高性能实时绘图 |
| pyserial | 3.5 | 串口 I/O |
| numpy | 2.2.4 | 矩阵运算 |
| scipy | 1.15.2 | RBF 插值、空间距离计算 |
| pytest | 8.3.5 | 单元测试框架 |

---

## 运行方法

```bash
# 启动主程序
python main.py
```

### 基本操作流程

1. **连接设备**：在左侧「串口」面板选择端口（如 `COM3`），点击「连接」
2. **查看实时数据**：中央热力图与右侧指标面板自动刷新（30 FPS 显示，200 Hz 采集）
3. **录制数据**：点击「开始录制」，CSV 文件保存至 `data/` 目录
4. **压力标定**：菜单 `工具 → 标定向导`，按 5 步完成标定并导出 JSON
5. **加载标定**：菜单 `文件 → 导入标定文件`，切换显示模式为「kPa」

---

## 项目结构

```
smart_insole/
│
├── main.py                        # 程序入口：日志初始化、全局异常钩子、启动窗口
├── config.py                      # 全局常量：串口参数、协议字段、ADC 配置、足底轮廓
├── requirements.txt               # Python 依赖
│
├── communication/                 # 通信层
│   ├── serial_manager.py          # QThread 串口读取线程（非阻塞 I/O、断线检测）
│   ├── protocol_parser.py         # 帧头同步、双子包合并、超时孤包清理
│   └── ring_buffer.py             # 循环缓冲区工具
│
├── data/                          # 数据处理层
│   ├── models.py                  # 领域数据类（RawPacket / MergedFrame / ProcessedFrame 等）
│   ├── data_processor.py          # ADC 解码、噪声过滤、标定换算、CoP/FPS 计算
│   ├── calibration_engine.py      # 标定状态机：掩码 → 零点 → 多点采集 → 分区线性拟合
│   └── data_recorder.py           # 异步 CSV 录制线程（队列生产-消费模式）
│
├── ui/                            # 表现层（PySide6）
│   ├── main_window.py             # 主窗口：布局编排、信号绑定、定时器限帧刷新
│   ├── serial_panel.py            # 端口选择、连接控制、状态显示
│   ├── heatmap_view.py            # 交互式热力图（RBF 插值、软边界、色图切换）
│   ├── metrics_panel.py           # 关键指标大字号面板（总压力、CoP、峰值、FPS）
│   ├── timeseries_view.py         # 滚动时序曲线（通道/区域选择、时间窗口）
│   ├── imu_view.py                # IMU 四元数 + 欧拉角显示（含可选 3D 姿态视图）
│   ├── calibration_wizard.py      # 5 步标定向导对话框
│   ├── data_control_panel.py      # 录制控制面板
│   └── styles.py                  # 深色主题 QSS 样式表
│
├── utils/
│   └── math_utils.py              # 四元数归一化、欧拉角转换
│
├── tests/                         # 测试套件
│   ├── test_protocol_parser.py    # 协议解析单元测试（8 用例）
│   ├── test_calibration.py        # 标定引擎测试
│   ├── test_data_processor.py     # 数据处理测试
│   ├── test_math_utils.py         # 数学函数测试
│   ├── test_ring_buffer.py        # 环形缓冲区测试
│   └── stress_test.py             # 200Hz 压力测试（5 分钟连续输入）
│
├── docs/
│   ├── 设计文档.md                # 架构设计、技术选型与改进思路
│   └── Git提交规范.md             # 提交信息格式约定
│
├── calibration_files/             # 标定参数 JSON 存储目录
├── logs/                          # 运行日志（app.log / comm.log）
└── data/                          # CSV 录制输出目录
```

---

## 运行测试

```bash
# 运行全部单元测试
pytest tests/ -v

# 运行 200Hz 压力测试（约 5 分钟）
python tests/stress_test.py
```

---

## 常见问题

| 现象 | 原因与处理 |
|------|------------|
| 串口连接失败 | 端口被其他程序占用；关闭后点击「刷新」重新扫描 |
| 运行中意外断开 | 系统自动检测并进入重连状态，状态栏显示 `reconnect_count` 递增 |
| 热力图全为 0 | 检查硬件是否正常输出数据，或确认 ADC 噪声阈值设置（默认 10） |
| 标定 R² 偏低 | 采集时砝码未平稳放置，或采集时长过短；建议 ≥3 秒/点 |
| 程序异常退出 | 查看 `logs/app.log` 与 `logs/comm.log` 获取详细堆栈信息 |

---

## 协议说明（简要）

硬件以 921600 baud 发送二进制帧，每帧由两个子包组成：

```
子包格式：[0xAA 0x55 0x03 0x99] [SEQ:1B] [SensorType:1B] [Payload]
  PACK1（SEQ=0x01）：128 字节 ADC 数据（前半）
  PACK2（SEQ=0x02）：144 字节（ADC 续 + 16 字节 IMU 四元数 float32×4）
合并后有效载荷：128 字节 ADC（8行×16列）+ 16 字节 IMU（w,x,y,z）
```

---

## 文档

- [设计文档](docs/设计文档.md) — 架构图、技术选型、已知限制
- [Git 提交规范](docs/Git提交规范.md) — 提交信息格式约定
