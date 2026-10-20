# WUTA-FSD-CLI

WUTA 实车启动管理的 Rich/Textual 纯键盘 CLI/TUI，独立 Git 仓库，作为
`WUTA2026_FINAL` 的 `fsd_startup` 子模块使用。保留原目录路径、启动入口、Mocha主题、
权限处理、检查和所属进程清理行为。

## 仓库与宿主集成

- CLI 仓库：<https://github.com/starry1N/WUTA-FSD-CLI>
- 宿主项目：<https://github.com/707GLobal/WUTA2026_FINAL>
- 宿主根入口：`start_fsd_manager.sh`；实际实车编排仍由 `start_full_fsd.sh` 负责。

从宿主仓库根目录初始化：

```bash
git submodule update --init --recursive
bash fsd_startup/install_ui.sh
```

以下操作命令均从宿主仓库根目录执行。单独克隆 CLI 仓库用于维护源码；运行预检查、
ROS遥测或实车编排及部分集成测试，仍需要宿主的 `tools/`、模块源码/配置和已安装的ROS驱动。
本仓库不复制这些算法、配置来源或硬件启动器。

本地 `sudo_askpass.local.sh`、缓存及运行记录不纳入 CLI 仓库。现有机器的本地认证文件保留；
新克隆需自行配置该文件及 `700` 权限，或使用机器已有 sudo 认证。提交 CLI 后需在宿主更新
子模块提交指针，宿主更新不自动包含 CLI 未提交内容。

## 操作说明

2026-10-14 拆分仓库；前次变更与验证范围见[宿主工作记录](https://github.com/707GLobal/WUTA2026_FINAL/blob/main/docs/工作记录_2026-10-13.md)。

入口是根目录 `./start_fsd_manager.sh`，复用原 `start_full_fsd.sh` 的部署配置和有依赖的启动顺序。
开发与维护统一保留在宿主 `docs/`，见 [开发指南](https://github.com/707GLobal/WUTA2026_FINAL/blob/main/docs/DEVELOPMENT.md#startup-development)。
默认使用 Rich + Textual 的纯键盘终端界面，操作、检查、车辆状态、传感器参数和日志均在一个终端内。
默认立即尝试启动；首次建议用菜单模式先查看检查结果。界面关闭鼠标操作；新增E键参数编辑页通过Tab/Enter操作按钮。

```bash
./start_fsd_manager.sh --menu                    # 单终端菜单，暂不启动车辆
./start_fsd_manager.sh --check --no-rviz         # 并行只读检查，返回汇总退出码
./start_fsd_manager.sh --skip-build              # 启动实车全栈，默认含 RViz
./start_fsd_manager.sh --sensor-only --no-rviz   # 传感器链，无规划控制
./start_fsd_manager.sh --build-only              # 强制构建，不连接硬件
./start_fsd_manager.sh --status
./start_fsd_manager.sh --stop                    # 请求管理器清理并退出
```

原脚本的模型、串口、外参、控制器和 CAN 配置等参数继续透传。
管理包自己的选项为 `--menu`、`--headless`、`--plain`、`--no-window`、`--no-color`、`--check`、`--status`、`--stop`。
默认需要交互终端；无终端常驻管理使用 `--headless --menu`。非交互环境也可执行只读 `--check`。没有图形桌面时使用 `--no-rviz`，终端内仍可查看状态。
`--no-window` 在新界面中禁用后台状态采集；`--plain` 保留旧逐行菜单及旧 Tk 窗口。
界面依赖独立安装在 `.runtime/fsd_manager/ui_deps`，不会添加到 ROS 子进程的 Python 搜索路径。
重新安装依赖执行 `bash fsd_startup/install_ui.sh`；版本在 `requirements-ui.txt` 固定。

## 开机自启

本机已安装 `~/.config/autostart/fsd-manager.desktop`。GNOME 桌面登录后等待10秒，
通过 `autostart.sh` 打开彩色管理终端，自动执行 `start_fsd_manager.sh --skip-build`，
状态与日志显示在同一终端，空间可视化仍由默认 RViz 展示。系统现有 GDM 配置已自动登录 wuta，因此开机即可触发。
自启复用已构建产物，失败保留菜单，运行中故障不自动重启控制链。
管理器已运行时不会打开第二个终端。q 退出后，本次桌面会话不会自动重新启动它。

禁用自启可将 `~/.config/autostart/fsd-manager.desktop` 中
`X-GNOME-Autostart-enabled=true` 改为 `false`。
更改自启参数可修改 `autostart.sh`；等待时间默认10秒，可用环境变量 `FSD_AUTOSTART_DELAY` 覆盖。

## 菜单

界面左侧用 ↑↓ 选择页面，Enter 打开；Tab / Shift-Tab 切换焦点。
检查表用 ↑↓ 选择模块，Enter 显示完整错误堆栈和原因；日志可用 PageUp / PageDown 滚动。
组件日志选择器用 Enter 展开、↑↓ 选择、Enter 确认。无需鼠标。
模块配置页使用相同的选择器和键盘操作，选择控制器、CAN、感知、建图、规划、定位或任务模块，
也可选择“全部配置清单”。选项来自现有配置审计清单；显示对应源文件路径和清单记录的参数，
相机/CAN额外显示当前部署选择。切换页面和清单刷新保留当前选择；缺失或无效清单会提示重新检查。

| 按键 | 操作 |
|---|---|
| s | 启动 / 修复后重试 |
| c | 并行预检查，汇总所有错误 |
| p | sudo 认证及华测串口权限处理 |
| x / Ctrl-C | 停止本次运行并清理登记进程，保留终端界面 |
| q / Ctrl-Q | 清理运行和采集进程并退出 |
| Space | 暂停 / 恢复日志刷新 |

界面不提供命令输入框或数字页面快捷键。Tab / Shift-Tab 切换区域，
在左侧页面菜单用方向键选择、Enter 打开；底部仅显示快捷键提示。
启动、检查、清理使用同一个后台工作线程串行操作，独立检查内部并行；
耗时操作期间界面可继续浏览，停止和退出会排队执行，不会与启动操作同时修改进程。

交互模式发生检查、启动或运行错误时，显示异常堆栈、命令、退出码及原脚本的组件日志。
原脚本发生致命启动错误仍会停止其运行栈，管理器继续保留菜单供修复和重试。
不会自动重启控制器，也不会继续启动依赖失败组件的下游节点。
`--check` 是专用于脚本/CI的只读模式，完成全部检查后按成功/失败返回 0/1。

## 并行与依赖

预检查已按 `start_full_fsd.sh` 的实际条件扩展为11组：模块配置、ROS部署、华测串口、
M1网络、CAN硬件、外参与TF、RViz部署与桌面、工作空间产物、CAN桥占用、原启动器单实例、
只读任务监控文件。独立项目在线程池中并行执行，任一失败不会取消其他检查。
`--reuse-ins` 仍检查指定串口可读写，仅跳过独占检查，与原脚本一致。
RViz 开关和 build/skip-build 采用最后一个参数生效的原脚本规则。
未构建产物在自动构建模式显示“待构建”，不是“构建通过”；skip-build 缺产物则失败。
任务监控脚本缺失与原脚本一致仅警告，不阻止车辆模块启动。

同一检查表还列出 sudo、工作空间构建、环境加载、CAN初始化、全部模块进程、
只读任务监控，以及雷达、图像、惯导、融合、定位、任务状态六个数据检查。
这些启动阶段检查直接读取原脚本的进度输出，未执行时显示“待启动验证”，
只读预检查不会为了验证它们启动硬件。进程“已启动”不等于话题“已收到消息”。
sensor-only、reuse-ins、no-rviz、build-only 对不执行项显示“跳过”及原因。
运行停止后进程显示“已停止”，保留启动验证历史供查看。

启动包设置 `FSD_PARALLEL_CHECKS=1`，让原脚本的
M1、相机、惯导首帧检查并行进行，之后检查融合输出；定位、规划控制仍保留原来的依赖顺序。
管理包的 sensor-only 模式也检查已启动的惯导输出。
直接运行旧入口时仍使用原来的顺序检查。

## 惯导与 GNSS 门控

华测桥的 C++ 默认值、YAML、launch 及独立启动脚本均使用 `min_gnss_status=0`。
GNSS为0不会因状态门槛停止发布，CLI仍按原流程订阅`/chcnav/odometry`，
没有额外串口读取或启动阶段的GNSS等待程序。
非有限数值和非法标准差的原有过滤仍保留。
自动定位原点在状态4时才固定，避免将GNSS=0的零经纬度永久作为原点。

任务机以`/chcnav/devpvt`原始ROS消息判断惯导设备心跳；GNSS=0且原始数据持续到达时，
不会因为定位状态而判设备自检失败。原始数据真正断流仍按现有超时处理。
状态机保持等待，车检模式允许新鲜的GNSS状态0或4进入READY并响应GO；其他模式及进入RACE仍要求状态4；
状态8不等同于状态4。原有任务选择、RES GO、雷达和定位门槛仍需满足。
传感器参数页通过ROS话题显示GNSS状态码及对应含义，任务页显示当前等待原因。

## 权限处理

已配置本机 `sudo_askpass.local.sh`，通过 `sudo -A` 自动认证，无需键入密码。
该文件权限为 700，已排除在 Git 提交之外；复制启动包到其他机器时需配置该本地文件。
密码不会进入命令行参数或日志。启动、p 操作、串口 ACL 和 root 残留清理均使用该认证。
CAN 沿用已有的 root 监管器创建/启用 vcan，
同接口仅有一个外部桥时验证并复用，退出 FSD 时保留外部桥；没有桥时创建本次运行的桥。
CAN 接口存在不表示已收到 VCU 报文；
请在组件日志中观察桥初始化和 VCU->FSD 计数。

华测串口按设备真实路径检查。如果当前用户没有读写权限，执行
`sudo setfacl -m u:<当前UID>:rw <串口>`，不设置全用户 666 权限。
需要系统提供 `setfacl`（Ubuntu 的 acl 包）；失败时保留错误详情和菜单。
ACL 用于当前设备节点，重插后可能需要重新处理。`--reuse-ins` 不授予外部串口权限，
但旧入口仍要求指定的串口存在且当前用户可读写；请传入外部链路实际使用的 `--ins-port`。

管理器持有 `flock` 单实例锁，每 250ms 跟踪启动子树，将 PID 与 Linux 进程启动时间保存在
`.runtime/fsd_manager/processes.json`。退出先请求原脚本正常清理，再对登记残留依次发送
INT、TERM、KILL；root 进程使用自动认证的 `sudo -A kill`。旧会话崩溃后，下次进入菜单会清理仍匹配
身份的登记残留。保留 `--reuse-ins` 的外部链路及其他不属于本次启动的 ROS 进程。
无法清理时保留登记记录和菜单，可用 p 重新认证后再 x / q，不将失败清理报告为成功。
本功能不使用全局 pkill；无法承诺清理登记前已脱离父进程的极短生命周期子树。

## 终端内实时状态与日志

页面包括启动检查、车辆状态、传感器参数、实时日志、组件日志、模块配置。
采用 Catppuccin Mocha 深色低饱和主题：紫色标题、青绿色强调、柔和灰白正文；
绿色标记成功/在线，黄色标记等待/超时，红色标记错误。
检查表的状态逐项更新，Enter 展开完整详情；错误不会把操作菜单冲出屏幕。
80×24 的终端也可使用，窄终端缩小左侧菜单宽度，保留Tab与方向键页面操作。

车辆页显示任务门控、模式、GO/急停广播、设备自检、控制请求。
控制请求值不代表执行器实测反馈，任务门控以状态机诊断为准。
车检GNSS门控显示“不要求（车检）”，设备心跳自检与GO要求保留；其他赛项继续按任务机诊断显示。
传感器页显示GNSS状态码及含义、点云数量、图像分辨率/编码、惯导位置速度、融合锥桶数、
最近5秒订阅接收频率与距末帧时间。后台 ROS 进程只有订阅者，不发送控制消息。
GNSS门控消费任务机权威诊断，不单凭原始状态码判断；未收到或超过3秒未更新诊断时显示未知。
不显示图像、点云或轨迹，与 RViz 的空间可视化分工。
状态采集在独立系统 Python 进程中运行，ROS 依赖与 Textual 依赖隔离；
采集错误及超过3秒未更新会在终端内显示。

日志沿用运行归档结构，组件日志页自动读取当前 `module_log_dir`。
配置页读取模块清单，不将清单声称为节点实际加载参数。

### 传感器参数页是否保存历史日志

当前页面读取 `.runtime/fsd_manager/telemetry.json` 的 `sensors` 字段，包含 GNSS、惯导、
雷达、相机和融合的最新显示内容。后台每0.5秒覆盖更新文件，重启采集时清除旧文件；
它是实时状态缓存，不是历史日志，不会随车辆运行目录归档。

目前没有专门追加保存传感器参数页的历史 log/CSV 文件，页面中的接收频率、末帧间隔、
在线/超时状态和传感器摘要无法仅靠此缓存回放。
相关设备日志位于本次运行的 `external_log/perception_drivers.log`、
`fsd_modules/perception/perception.log`、`chcnav_log/driver.log`；
华测数据记录位于 `chcnav_log/<时间戳>/`。这些记录与页面内容不是一一对应关系。
任务状态变化及设备自检事件统一写入 `manager.log`，完整日志目录说明见
[运行日志](https://github.com/707GLobal/WUTA2026_FINAL/blob/main/docs/LOGGING.md)。

## 验证

```bash
/usr/bin/python3 -m pytest -q fsd_startup/test_startup.py fsd_startup/test_terminal_ui.py fsd_startup/test_check_alignment.py \
  fsd_startup/test_logging.py fsd_startup/test_mode_cache.py \
  tools/test_can_reconnect.py tools/test_privileged_group.py tools/test_chcnav_serial_guard.py
bash -n start_fsd_manager.sh start_full_fsd.sh fsd_startup/window.sh
```

测试覆盖并行检查的全错误收集、并行话题检查不触发 supervisor 清理、
失败后保留菜单、PID复用防护、脱离进程组的残留清理和外部进程保留。
测试不打开 USB CAN、不写串口、不发送车辆控制帧。

## 统一日志与归档

每次 s 启动（含预检查失败）生成独立运行目录；启动前读取 ZLG 模式缓存，
正常直接创建 wuta_logs/<赛项>/<YYYYmmdd_HHMMSS>；缓存不可用才先写 pending 后归档。
未运行时管理事件写入 wuta_logs/sessions。
管理事件和任务监控统一进入 manager.log，不再生成 mission_monitor.log。
终端与图形组件日志页共用`dashboard.component_log_files`，递归读取本次运行的`fsd_modules/`、`external_log/`、`chcnav_log/`、`zlgCAN_log/`，兼容旧`modules/`及`module_log_dir`。下拉项显示相对目录，区分不同组的同名日志；新运行切换绝对路径，新增文件时保持仍有效的选择。
启动检查页分别显示`perception_drivers`（ZED/M1驱动组）和`perception`（算法组）；进程已启动不替代图像/点云首帧验证。
完整目录和职责说明见 [运行日志](https://github.com/707GLobal/WUTA2026_FINAL/blob/main/docs/LOGGING.md)。

## E22完整实时日志与传感器状态（2026-10-19）

CLI仍由既有Manager/独立全栈输出收集器写日志。在`manager.log`旁同步追加`manager.events.jsonl`，包含CLI事件Unix纳秒时间、等级和完整文字，多行堆栈不截断；这是同一写入者的结构化副本，不是第二个运行管理器。该文件随原运行目录一起归档。CLI原有界面和任务控制语义不变。

只读采集器继续使用原有ROS订阅，在`telemetry.json`增加`sensors_data`、`vehicle_data`、`source_stamp_ns`和采集器错误；每项保留Header时间或显式未知，并记录源端接收时间。GNSS、惯导、雷达、相机、融合的详情沿用CLI，不把图像/点云放入JSON。采集缓存依旧0.5秒更新；无线发送率由无线组件独立限速。

0.5.0起按用户要求只转发必要信息：原日志所有者额外生成`manager.radio.events.jsonl`，由`log_context.py:necessary_radio_event`筛选错误、警告及其连续诊断上下文、任务监控变化和启动/退出汇总；菜单/窗口操作、逐项成功、启动等待和普通构建进度只保留在本地全文中。两种journal使用不同stream ID，已选事件保留完整文字和原源时间；旧全文journal不自动作为新无线源。Manager状态文件的`radio_log_events`指向当前必要journal。

无线组件0.5.0读取必要事件增量及原传感器快照，PC落盘确认后推进日志断点。关键日志突发仍可能积压，不以删除已选事件追赶实时。详情见主项目显示子模块`radio_link/README.md`。Linux拉取时同时更新`fsd_startup`和`fsd-visualization-code`，CLI与无线进程需按原流程重启；旧进程不会自动加载新规则。

新`wuta_logs/`布局需配合无线0.5.1：扫描新旧根目录及状态文件路径，日志归档移动后按stream ID继续处理磁盘确认；无线格式与源时间不变。Windows可运行`python -m pytest -q fsd_startup/test_log_views.py`验证日志列表和进程检查映射，无需导入Linux Manager；完整交互回归仍使用原`test_terminal_ui.py`在Linux运行。

## 当次启动无线日志（0.6.0）

CLI打开时由Manager清空无线运行选择，每次按`s`创建RunLog后，由原日志所有者发布`.runtime/fsd_manager/radio_run.json`；Manager状态的`radio_run`保留同一scope、必要journal路径、源纳秒时间及运行状态。结束归档只更新当前scope的路径，不把较旧运行重新选为当前。直接全栈入口也复用RunLog选择；仿真不替换实车选择。

无线0.6.0仅传此指针指定的运行，不补历史目录。新启动切换待发队列并重置Foxglove会话，终端日志历史同步清空；图形日志窗口结束后保留本次manager.log。Linux的全文文件不删除。普通GNSS状态切换由传感器快照发送，必要日志不再重复这些info行；错误/警告及关键任务事件继续保留。

配合115200串口、62.5 kbps模块空速与3000 UART字节/秒双向预算，详情见显示子模块radio_link/README.md。CLI与收发两端需同时更新；缺少运行选择时无线端提示重启新版CLI，不回退历史补传。

## 0.6.2：当次CLI完整日志（当前策略）

按用户要求，当前运行的radio_run.journal、run.json的manager_radio_events及Manager状态radio_log_events改为完整的manager.events.jsonl。所有写入当次CLI主日志的事件均转发，包含普通info、GNSS状态、检查/启动进度、构建输出及完整多行错误，不再受必要事件规则筛选。旧manager.radio.events.jsonl仍可留作兼容产物，但不再是新版运行的无线源。

仅跟随当次运行，不遍历历史运行；组件独立文件不额外批量上传，只有原本进入CLI主日志的内容走此完整事件流。源时间、落盘确认、断点及新运行清理旧显示机制保持。Linux需要同时拉取显示和CLI子模块，重启CLI与无线发送进程后生效。

## CLI统一配置与远程操作（2026-10-20）

本地按E进入参数编辑，选择模块和完整YAML路径，输入JSON值，Tab/Enter暂存、保存。跨模块草稿一次校验提交；未保存时可Esc退出。原模块配置页仍是manifest审计快照，编辑页直接读取所选源文件。

统一API在Manager原工作线程串行执行，`control_api.py`接收文件邮箱，`config_store.py`复用宿主tools的目录与一致性校验。文件保存使用SHA256版本检查、保留注释的标量补丁、事务备份与原子替换；不热改运行算法，不自动重启。支持标量及定长标量数组，不新增/删除YAML结构。保存后待确认加载状态保守持久保留。

主仓库根可执行 `python3 fsd_startup/control_api.py config.list`、`config.read --module controller`、`config.set --updates '<JSON列表>'` 以及 `cli.status`、`cli.check`、`cli.start`、`cli.stop`。原请求结果查询：`cli.result --request-id <32位ID>`。调用者只投递邮箱，不自行启动进程。

无线0.7.0通过现有E22双向扩展调用同一接口，Foxglove Parameters编辑PC草稿，Publish按钮提交保存/检查/启动/停止。Linux CLI需常驻；例如 `bash start_fsd_manager.sh --headless --menu --skip-build --no-rviz`，保留现场原部署参数。CLI stop操作停止所属FSD进程并保留管理器，根入口 `--stop` 仍清理并退出管理器。无线程序独立启动和保留。启动返回表示启动流程已提交，全栈就绪看phase和日志。

持久邮箱在 `.runtime/fsd_manager/control/`：inbox请求、results结果、heartbeat.json状态、transactions备份。UUID去重、boot及停止run绑定、到期限制防止迟到请求重复执行；超时结果未知需查原ID。不要在在途请求期间清理邮箱或结果。详细模块来源、字段、限制和部署步骤见宿主 [FOXGLOVE_PARAMETERS](https://github.com/707GLobal/WUTA2026_FINAL/blob/main/docs/FOXGLOVE_PARAMETERS.md)。

本轮仅完成源码实现与人工阅读，按用户要求未运行测试、构建、WSL或实机操作；未改动现场YAML，需配套更新宿主、CLI和显示子模块并重启加载。

无线0.7.1配套：邮箱优先执行待处理的cli.check/start/stop/status/result及config.set，再处理config.list/read；同级保持到达顺序，仍由Manager原工作线程串行执行，不能抢断正在进行的操作。指令与结果的无线优先级由显示子模块独立commands队列负责，CLI不直接读写串口。未运行测试或实机操作。
