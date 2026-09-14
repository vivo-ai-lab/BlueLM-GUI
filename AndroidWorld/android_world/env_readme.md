# AndroidWorld Docker 环境管理

本文档说明如何基于本仓库构建 AndroidWorld Docker 镜像，并按**端口范围**批量创建 / 删除 Android 模拟器容器。每个容器对外只暴露一个 **server 端口**（映射到容器内 5000 端口），端口范围内的每个端口对应一个独立容器。

## 目录

- [1. 环境要求](#1-环境要求)
- [2. 构建镜像](#2-构建镜像)
- [3. 批量创建容器](#3-批量创建容器)
- [4. 批量删除容器](#4-批量删除容器)
- [5. 常用运维命令](#5-常用运维命令)
- [6. 常见问题](#6-常见问题)

## 1. 环境要求

- Linux 主机（推荐），需支持 KVM 硬件加速（`/dev/kvm` 可用）
- Docker ≥ 20.10（BuildKit 开启）
- 磁盘空间建议 ≥ 50GB（镜像约 15~20GB，每个容器运行时的模拟器镜像另占数 GB）

验证 KVM 是否可用：

```bash
ls -l /dev/kvm
```

若不可用，容器内模拟器会退化为软件加速（`-accel off`），启动极慢，仅适合验证。

## 2. 构建镜像

在仓库根目录执行：

```bash
./scripts/build_image.sh
```

默认构建 `android_world:latest`。常用变体：

```bash
# 指定 tag
./scripts/build_image.sh mytag

# 指定 tag 并禁用缓存（依赖或 SDK 变更后强制重编）
./scripts/build_image.sh mytag --no-cache

# 自定义镜像名
IMAGE_NAME=android_world:dev ./scripts/build_image.sh
```

构建镜像时会预下载 Android SDK、系统镜像（android-33 google_apis x86_64）以及全部 App APK，耗时较长（首次约 20~40 分钟），请耐心等待。

> 提示：构建参数 `PIP_INDEX_URL` 默认使用清华 PyPI 镜像（见 `Dockerfile`），如需更换可 `docker build --build-arg PIP_INDEX_URL=...`。

## 3. 批量创建容器

按端口范围批量创建容器，**范围中的每个端口对应一个容器**：

```bash
./scripts/create_containers.sh <START_PORT> <END_PORT>
```

示例 —— 创建 64 个容器，host 端口 5001 ~ 5064：

```bash
./scripts/create_containers.sh 5001 5064
```

每个容器的命名规则为 `android_world_<端口>`，端口映射关系：

| 容器名 | Host 端口 | 容器内端口 | 用途 |
| --- | --- | --- | --- |
| `android_world_5001` | 5001 | 5000 | FastAPI server（HTTP API） |
| `android_world_5002` | 5002 | 5000 | FastAPI server（HTTP API） |
| ... | ... | ... | ... |

即：`docker run -d --name android_world_5001 --privileged -p 5001:5000 android_world:latest`。

容器启动时自动完成：启动无头模拟器（`-no-window -no-snapshot -no-boot-anim -grpc 8554`）→ `adb root` → 启动 FastAPI server（`server.android_server`，监听 5000）。

### 常用参数（环境变量）

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `IMAGE_NAME` | `android_world:latest` | 指定运行的镜像 |
| `CONTAINER_PREFIX` | `android_world` | 容器名前缀 |
| `DRY_RUN` | `0` | 设为 `1` 只打印命令不执行 |

```bash
# 使用指定镜像创建 4 个容器
IMAGE_NAME=android_world:dev ./scripts/create_containers.sh 5001 5004

# 演练模式，只打印将要执行的 docker 命令
DRY_RUN=1 ./scripts/create_containers.sh 5001 5004
```

### 验证容器

```bash
docker ps --filter name=android_world_
```

每个容器的 FastAPI server 就绪后（模拟器 boot 完成 + server 启动，约 5~10 分钟），可通过 HTTP 健康检查：

```bash
curl http://localhost:5001/health
# {"status":"success"}
```

## 4. 批量删除容器

### 按端口范围删除

```bash
./scripts/remove_containers.sh <START_PORT> <END_PORT>
```

示例 —— 删除端口 5001 ~ 5064 对应的容器：

```bash
./scripts/remove_containers.sh 5001 5064
```

### 删除全部容器

```bash
./scripts/remove_containers.sh --all
```

> 注意：`--all` 会删除所有 `android_world_` 前缀的容器（无论端口），请谨慎使用。

### 常用参数

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CONTAINER_PREFIX` | `android_world` | 容器名前缀 |
| `DRY_RUN` | `0` | 设为 `1` 只打印命令不执行 |

## 5. 常用运维命令

```bash
# 查看所有容器及端口映射
docker ps -a --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"

# 查看单个容器日志（模拟器 boot 与 server 启动过程）
docker logs -f android_world_5001

# 进入容器
docker exec -it android_world_5001 bash

# 停止/启动单个容器
docker stop android_world_5001
docker start android_world_5001

# 停止/启动全部容器
docker stop $(docker ps -q --filter name=android_world_)
docker start $(docker ps -q --filter name=android_world_)
```

## 6. 常见问题

### 容器启动后 /health 一直不可用

模拟器首次 boot 较慢（日志中可见 `Boot completed in ... ms`）。等待 5~10 分钟后重试：

```bash
docker logs android_world_5001 | grep -i "boot completed"
```

### 容器退出 / 反复重启

多为模拟器启动失败（KVM 不可用、内存不足、端口被占）。查看日志定位：

```bash
docker logs android_world_5001
```

确认宿主机 KVM：`ls -l /dev/kvm`；确认端口未被占用：`ss -ltn | grep 5001`。

### 端口被占用

创建容器时若 host 端口已被占用，`docker run` 会失败。可先删除占用端口的旧容器，或换一个端口范围。

### 重新构建镜像后容器未更新

镜像构建完成后，需删除并重建容器（`remove_containers.sh` + `create_containers.sh`），`docker start` 不会使用新镜像。