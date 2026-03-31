# Walking Assistant Robot - Control System

## 프로젝트 개요

실내 반자율형 보행 보조 로봇을 위한 웹 기반 제어 및 모니터링 시스템입니다.

### 주요 기능
- 웹 UI 를 통한 목적지 설정
- LiDAR 기반 장애물 회피
- 실시간 로봇 상태 모니터링
- WebSocket 을 통한 실시간 데이터 동기화

## 하드웨어 스택

### 메인 컨트롤러
- **Raspberry Pi 4** (4GB)
  - OS: ROS2 Humble, Python 3.10

### 서브 컨트롤러
- **Arduino Mega 2560**
  - PID 모터 제어
  - 센서 허브

### 센서
- **LD19 LiDAR** - 12m 범위
- **Pi Camera V2**
- **HX711 Load Cell ×2**
- **MPU-9250 IMU**
- **HC-SR04 Ultrasonic ×2**

### 통신
- **Pi ↔ Arduino**: UART (230400bps)
- **Frontend ↔ Backend**: WebSocket

## 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| **Frontend** | React + TypeScript | Vite, TailwindCSS |
| **State Management** | Zustand | 경량 글로벌 스토어 |
| **Map/Visualization** | HTML5 Canvas | LiDAR 포인트 렌더링 |
| **Backend** | FastAPI (Python) | Async 지원, WebSocket 네이티브 |
| **Database** | SQLite (dev) / PostgreSQL (prod) | 로봇 로그, 목적지 이력 저장 |
| **Communication** | WebSocket + REST API | 실시간 제어 WS, 설정/로그 REST |
| **Robot Control** | ROS2 Humble (Python) | ldrobot_lidar, pyserial, rclpy |
| **Algorithm** | A* / Simplified DWA | 기본: 장애물 감지 + 단순 우회 |

## 프로젝트 구조

```
emba/
├── backend/
│   ├── main.py                    # FastAPI 애플리케이션 엔트리 포인트
│   ├── requirements.txt           # Python 의존성
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # 애플리케이션 설정
│   │   └── security.py            # 인증/인가 (선택)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── robot_schemas.py       # 로봇 상태 스키마
│   │   └── log_schemas.py         # 로그 스키마
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── robot.py               # 로봇 제어 엔드포인트
│   │   └── logs.py                # 로그 엔드포인트
│   └── ros2/
│       ├── __init__.py
│       └── ros2_bridge_interface.py  # ROS2 브릿지 인터페이스
├── frontend/
│   ├── package.json               # Node.js 의존성
│   ├── vite.config.ts             # Vite 설정
│   ├── tailwind.config.js         # TailwindCSS 설정
│   ├── postcss.config.js          # PostCSS 설정
│   ├── index.html                 # HTML 엔트리 포인트
│   ├── tsconfig.json              # TypeScript 설정
│   ├── tsconfig.node.json         # Node.js TypeScript 설정
│   └── src/
│       ├── main.tsx               # React 애플리케이션 엔트리
│       ├── App.tsx                # 메인 애플리케이션 컴포넌트
│       ├── index.css              # 전역 스타일
│       ├── types/
│       │   ├── __init__.py
│       │   └── robot.types.ts     # TypeScript 타입 정의
│       ├── store/
│       │   ├── __init__.py
│       │   └── useRobotStore.ts   # Zustand 스토어
│       ├── hooks/
│       │   ├── __init__.py
│       │   └── useRobotWebSocket.ts  # WebSocket 커스텀 훅
│       └── components/
│           ├── __init__.py
│           ├── lidar/
│           │   ├── __init__.py
│           │   └── LidarCanvas.tsx    # LiDAR 시각화
│           ├── map/
│           │   ├── __init__.py
│           │   └── RobotMap.tsx       # 로봇 맵
│           ├── controls/
│           │   ├── __init__.py
│           │   └── ControlPanel.tsx   # 제어 패널
│           ├── status/
│           │   ├── __init__.py
│           │   └── StatusPanel.tsx    # 상태 패널
│           └── layout/
│               ├── __init__.py
│               └── MainLayout.tsx     # 메인 레이아웃
└── README.md                      # 이 파일
```

## 설치 및 실행

### Backend 설치

```bash
cd emba/backend
pip install -r requirements.txt
```

### Frontend 설치

```bash
cd emba/frontend
npm install
```

### Frontend 실행

```bash
cd emba/frontend
npm run dev
```

### Backend 실행

```bash
cd emba/backend
python main.py
```

## API 엔드포인트

### WebSocket
- `ws://localhost:8000/ws/robot/control`
  - **메시지 수신**: `{"cmd": "navigate", "target": {"x": 2.5, "y": 1.0}}`
  - **메시지 전송**: `{"battery": 12.4, "obstacle_ahead": false, "status": "moving", "position": {"x": 1.2, "y": 0.8}}`

### REST API

#### POST /api/destination
목적지 설정
```json
{
  "x": 2.5,
  "y": 1.0
}
```

#### GET /api/robot/status
로봇 현재 상태 조회

#### GET /api/logs
로봇 로그 조회 (페이징 지원)

#### POST /api/emergency_stop
비상 정지 명령

## 개발 가이드

### Frontend

#### Zustand Store 사용
```typescript
import { useRobotStore } from './store/useRobotStore';

const { position, setDestination, emergencyStop } = useRobotStore();
```

#### WebSocket Hook 사용
```typescript
import { useRobotWebSocket } from './hooks/useRobotWebSocket';

const { socket, navigate, emergencyStop } = useRobotWebSocket();
```

### Backend

#### FastAPI 앱 생성
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### Pydantic 스키마 사용
```python
from pydantic import BaseModel, Field

class Destination(BaseModel):
    x: float = Field(..., ge=-10, le=10)
    y: float = Field(..., ge=-10, le=10)
```

## 제한 사항

- 완전 자율 주행 아님 (반자율 가이드 모드)
- 실내 평면 환경에서만 작동
- 저속 주행 (0.3-0.5m/s)

## 라이선스

MIT License