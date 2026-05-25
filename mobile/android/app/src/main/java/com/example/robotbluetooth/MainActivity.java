package com.example.robotbluetooth;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.content.BroadcastReceiver;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.Base64;
import android.util.Log;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

public class MainActivity extends Activity {
    private static final String TAG = "RobotBluetooth";
    private static final UUID SPP_UUID =
            UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
    private static final String PREFS = "robot_bluetooth";
    private static final String PREF_BT_FEATURE_ENABLED = "bt_feature_enabled";
    private static final String PREF_MANUAL_SPEED = "manual_speed";
    private static final String SCREEN_MAIN = "main";
    private static final String SCREEN_BLUETOOTH = "bluetooth";
    private static final String SCREEN_MANUAL = "manual";
    private static final String SCREEN_AUTO = "auto";
    private static final String SCREEN_MAP = "map";
    private static final String SCREEN_MISC = "misc";
    private static final long MAP_SCAN_INTERVAL_MS = 100;
    private static final long OBJECT_DETECT_INTERVAL_MS = 500;
    private static final long ULTRASONIC_INTERVAL_MS = 200;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Object ioLock = new Object();
    private final List<BluetoothDevice> devices = new ArrayList<>();
    private final Set<String> expandedDevices = new HashSet<>();
    private final StringBuilder logBuffer = new StringBuilder();
    private final SimpleDateFormat logTimeFormat = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US);

    private SharedPreferences prefs;
    private BluetoothAdapter bluetoothAdapter;
    private BluetoothSocket socket;
    private InputStream input;
    private OutputStream output;
    private volatile boolean connected = false;
    private volatile boolean scanInProgress = false;
    private volatile boolean connectInProgress = false;
    private String connectedMac;
    private String pendingConnectMac;
    private String currentScreen = SCREEN_MAIN;

    private TextView mainStatusText;
    private TextView bluetoothStatusText;
    private TextView scanStatusText;
    private TextView logText;
    private TextView manualSpeedText;
    private TextView autoSpeedText;
    private TextView mapGoalText;
    private EditText kernelTokenInput;
    private EditText kernelCommandInput;
    private LocalMapView localMapView;
    private Button map2dButton;
    private Button map3dButton;
    private float selectedMapX = 0.0f;
    private float selectedMapY = 1.0f;
    private float[] lidarBins = new float[0];
    private boolean mapView3d = false;
    private volatile boolean mapAutoScanEnabled = false;
    private volatile boolean mapScanInFlight = false;
    private volatile boolean objectDetectInFlight = false;
    private volatile boolean ultrasonicInFlight = false;
    private long lastObjectDetectAt = 0;
    private long lastUltrasonicAt = 0;
    private LinearLayout deviceListContainer;
    private ImageView imageView;
    private Switch bluetoothFeatureSwitch;

    private final Runnable mapAutoScanRunnable = new Runnable() {
        @Override
        public void run() {
            if (!mapAutoScanEnabled || !SCREEN_MAP.equals(currentScreen)) {
                return;
            }
            requestMapScan(false);
            long now = System.currentTimeMillis();
            if (now - lastObjectDetectAt >= OBJECT_DETECT_INTERVAL_MS) {
                lastObjectDetectAt = now;
                requestRealtimeCommand("OBJECT_DETECT", false);
            }
            if (now - lastUltrasonicAt >= ULTRASONIC_INTERVAL_MS) {
                lastUltrasonicAt = now;
                requestRealtimeCommand("US", false);
            }
            mainHandler.postDelayed(this, MAP_SCAN_INTERVAL_MS);
        }
    };

    private final BroadcastReceiver bluetoothReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (BluetoothDevice.ACTION_FOUND.equals(action)) {
                BluetoothDevice device = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
                if (device != null) {
                    short rssi = intent.getShortExtra(BluetoothDevice.EXTRA_RSSI, Short.MIN_VALUE);
                    appendLog("기기 발견: " + describeDevice(device) + " rssi=" + rssi);
                    addOrUpdateDevice(device);
                }
            } else if (BluetoothAdapter.ACTION_DISCOVERY_FINISHED.equals(action)) {
                scanInProgress = false;
                appendLog("블루투스 검색 완료");
                refreshBluetoothStatus("검색 완료");
            } else if (BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(action)) {
                BluetoothDevice device = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
                int bondState = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.ERROR);
                int previousState = intent.getIntExtra(BluetoothDevice.EXTRA_PREVIOUS_BOND_STATE, BluetoothDevice.ERROR);
                if (device != null) {
                    appendLog("페어링 상태: " + describeDevice(device)
                            + " " + bondStateName(previousState) + " -> " + bondStateName(bondState));
                    addOrUpdateDevice(device);
                    if (device.getAddress().equals(pendingConnectMac)
                            && bondState == BluetoothDevice.BOND_BONDED) {
                        String mac = pendingConnectMac;
                        pendingConnectMac = null;
                        connectOnce(mac);
                    } else if (device.getAddress().equals(pendingConnectMac)
                            && bondState == BluetoothDevice.BOND_NONE) {
                        pendingConnectMac = null;
                        refreshBluetoothStatus("페어링 실패");
                    }
                }
            } else if (BluetoothAdapter.ACTION_STATE_CHANGED.equals(action)) {
                int state = intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR);
                appendLog("휴대폰 블루투스 상태: " + adapterStateName(state));
                refreshBluetoothStatus(null);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        bluetoothAdapter = BluetoothAdapter.getDefaultAdapter();
        closeConnection();
        registerBluetoothReceiver();
        requestBluetoothPermissions();
        appendLog("앱 시작: 자동 블루투스 연결은 사용하지 않습니다.");
        showMainScreen();
    }

    @Override
    protected void onDestroy() {
        stopMapAutoScan();
        if (bluetoothAdapter != null && hasBluetoothPermission() && bluetoothAdapter.isDiscovering()) {
            bluetoothAdapter.cancelDiscovery();
        }
        closeConnection();
        try {
            unregisterReceiver(bluetoothReceiver);
        } catch (Exception ignored) {
        }
        super.onDestroy();
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (isFinishing()) {
            closeConnection();
        }
    }

    @Override
    public void onBackPressed() {
        if (SCREEN_BLUETOOTH.equals(currentScreen)) {
            showMainScreen();
            return;
        }
        if (SCREEN_MANUAL.equals(currentScreen)) {
            showMainScreen();
            return;
        }
        if (SCREEN_AUTO.equals(currentScreen)) {
            showMainScreen();
            return;
        }
        if (SCREEN_MAP.equals(currentScreen)) {
            showMainScreen();
            return;
        }
        if (SCREEN_MISC.equals(currentScreen)) {
            showMainScreen();
            return;
        }
        closeConnection();
        super.onBackPressed();
    }

    private void registerBluetoothReceiver() {
        registerReceiver(bluetoothReceiver, new IntentFilter(BluetoothDevice.ACTION_FOUND));
        registerReceiver(bluetoothReceiver, new IntentFilter(BluetoothAdapter.ACTION_DISCOVERY_FINISHED));
        registerReceiver(bluetoothReceiver, new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED));
        registerReceiver(bluetoothReceiver, new IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED));
    }

    private void showMainScreen() {
        currentScreen = SCREEN_MAIN;
        stopMapAutoScan();
        LinearLayout root = verticalRoot();
        root.addView(toolbar("로봇 제어", false));

        mainStatusText = label("연결 안 됨", 18, Color.rgb(24, 24, 27));
        root.addView(mainStatusText);
        updateMainStatus();

        imageView = new ImageView(this);
        imageView.setAdjustViewBounds(true);
        imageView.setScaleType(ImageView.ScaleType.FIT_CENTER);
        imageView.setBackgroundColor(Color.rgb(244, 244, 245));
        root.addView(imageView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(240)
        ));

        View spacer = new View(this);
        root.addView(spacer, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(36)
        ));

        TextView modeTitle = label("동작 선택", 16, Color.rgb(39, 39, 42));
        modeTitle.setPadding(0, 0, 0, dp(8));
        root.addView(modeTitle);

        root.addView(modeGrid());

        setContentView(scroll(root));
    }

    private View modeGrid() {
        LinearLayout grid = new LinearLayout(this);
        grid.setOrientation(LinearLayout.VERTICAL);

        LinearLayout row1 = new LinearLayout(this);
        row1.setOrientation(LinearLayout.HORIZONTAL);
        Button manualButton = modeButton("수동조작", "모터 이동");
        manualButton.setOnClickListener(v -> showManualScreen());
        row1.addView(manualButton, modeButtonParams());

        Button autoButton = modeButton("자율주행", "LiDAR+카메라+초음파");
        autoButton.setOnClickListener(v -> showMapScreen());
        row1.addView(autoButton, modeButtonParams());
        grid.addView(row1);

        LinearLayout row2 = new LinearLayout(this);
        row2.setOrientation(LinearLayout.HORIZONTAL);
        Button miscButton = modeButton("커널 옵션", "Pi 관리자");
        miscButton.setOnClickListener(v -> showMiscScreen());
        row2.addView(miscButton, modeButtonParams());
        grid.addView(row2);

        return grid;
    }

    private LinearLayout.LayoutParams modeButtonParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(96), 1);
        params.setMargins(dp(4), dp(4), dp(4), dp(4));
        return params;
    }

    private Button modeButton(String title, String subtitle) {
        Button button = actionButton(title + "\n" + subtitle);
        button.setTextSize(15);
        return button;
    }

    private void showComingSoon(String name) {
        Toast.makeText(this, name + " 기능은 다음 단계에서 개발합니다.", Toast.LENGTH_SHORT).show();
        appendLog(name + " 선택됨: 아직 구현 전입니다.");
    }

    private void showAutoScreen() {
        currentScreen = SCREEN_AUTO;
        LinearLayout root = verticalRoot();
        root.addView(toolbar("근거리 회피", true));

        mainStatusText = label("연결 안 됨", 18, Color.rgb(24, 24, 27));
        root.addView(mainStatusText);
        updateMainStatus();

        TextView description = label("Arduino 초음파 3개로 바로 앞 장애물을 피하는 근거리 회피 테스트입니다.", 13, Color.rgb(82, 82, 91));
        description.setPadding(0, dp(8), 0, dp(16));
        root.addView(description);

        autoSpeedText = label("", 16, Color.rgb(24, 24, 27));
        root.addView(autoSpeedText);

        SeekBar speedBar = new SeekBar(this);
        speedBar.setMax(255);
        speedBar.setProgress(manualSpeed());
        speedBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                updateAutoSpeedText(progress);
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
                int speed = seekBar.getProgress();
                prefs.edit().putInt(PREF_MANUAL_SPEED, speed).apply();
                sendCommand("SPD " + speed);
            }
        });
        root.addView(speedBar, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));
        updateAutoSpeedText(manualSpeed());

        LinearLayout autoRow = new LinearLayout(this);
        autoRow.setOrientation(LinearLayout.HORIZONTAL);
        Button startButton = actionButton("자율 시작");
        startButton.setOnClickListener(v -> sendCommands("SPD " + manualSpeed(), "AUTO_ON"));
        autoRow.addView(startButton, new LinearLayout.LayoutParams(0, dp(72), 1));

        Button stopButton = actionButton("자율 정지");
        stopButton.setOnClickListener(v -> sendCommand("AUTO_OFF"));
        autoRow.addView(stopButton, new LinearLayout.LayoutParams(0, dp(72), 1));
        root.addView(autoRow);

        LinearLayout checkRow = new LinearLayout(this);
        checkRow.setOrientation(LinearLayout.HORIZONTAL);
        Button statusButton = actionButton("상태 확인");
        statusButton.setOnClickListener(v -> sendCommand("AUTO_STATUS"));
        checkRow.addView(statusButton, new LinearLayout.LayoutParams(0, dp(64), 1));

        Button distanceButton = actionButton("거리 확인");
        distanceButton.setOnClickListener(v -> sendCommand("US"));
        checkRow.addView(distanceButton, new LinearLayout.LayoutParams(0, dp(64), 1));
        root.addView(checkRow);

        Button perceptionButton = actionButton("카메라/LiDAR 상태");
        perceptionButton.setOnClickListener(v -> sendCommand("PERCEPTION_STATUS"));
        root.addView(perceptionButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(56)
        ));

        Button emergencyStopButton = actionButton("긴급 정지");
        emergencyStopButton.setOnClickListener(v -> sendStopCommand());
        root.addView(emergencyStopButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        LinearLayout logButtons = new LinearLayout(this);
        logButtons.setOrientation(LinearLayout.HORIZONTAL);
        Button copyLogButton = actionButton("로그 복사");
        copyLogButton.setOnClickListener(v -> copyLogsToClipboard());
        logButtons.addView(copyLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        Button clearLogButton = actionButton("지우기");
        clearLogButton.setOnClickListener(v -> clearLogs());
        logButtons.addView(clearLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        root.addView(logButtons);

        ScrollView logScroll = new ScrollView(this);
        logText = label(logBuffer.toString(), 12, Color.rgb(63, 63, 70));
        logScroll.addView(logText);
        root.addView(logScroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(240)
        ));

        setContentView(scroll(root));
    }

    private void showMapScreen() {
        stopMapAutoScan();
        currentScreen = SCREEN_MAP;
        LinearLayout root = verticalRoot();
        root.addView(toolbar("자율주행", true));

        mainStatusText = label("연결 안 됨", 18, Color.rgb(24, 24, 27));
        root.addView(mainStatusText);
        updateMainStatus();

        TextView description = label("LD19 LiDAR로 실시간 지도 맵핑, COCO 카메라 물체 인식, Arduino 초음파 3개 거리 확인을 함께 사용합니다.", 13, Color.rgb(82, 82, 91));
        description.setPadding(0, dp(8), 0, dp(12));
        root.addView(description);

        localMapView = new LocalMapView(this);
        localMapView.setGoal(selectedMapX, selectedMapY);
        localMapView.setPerspectiveMode(mapView3d);
        root.addView(localMapView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(320)
        ));

        LinearLayout viewModeRow = new LinearLayout(this);
        viewModeRow.setOrientation(LinearLayout.HORIZONTAL);
        map2dButton = actionButton("2D 지도");
        map2dButton.setOnClickListener(v -> setMapViewMode(false));
        viewModeRow.addView(map2dButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        map3dButton = actionButton("3D 보기");
        map3dButton.setOnClickListener(v -> setMapViewMode(true));
        viewModeRow.addView(map3dButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        root.addView(viewModeRow);
        updateMapViewModeButtons();

        mapGoalText = label("", 15, Color.rgb(24, 24, 27));
        mapGoalText.setPadding(0, dp(8), 0, dp(8));
        root.addView(mapGoalText);
        updateMapGoalText();

        LinearLayout row1 = new LinearLayout(this);
        row1.setOrientation(LinearLayout.HORIZONTAL);
        Button mapStatusButton = actionButton("통합 상태");
        mapStatusButton.setOnClickListener(v -> sendCommand("MAP_STATUS"));
        row1.addView(mapStatusButton, new LinearLayout.LayoutParams(0, dp(60), 1));

        Button mapScanButton = actionButton("실시간 스캔");
        mapScanButton.setOnClickListener(v -> requestMapScan(true));
        row1.addView(mapScanButton, new LinearLayout.LayoutParams(0, dp(60), 1));
        root.addView(row1);

        LinearLayout row2 = new LinearLayout(this);
        row2.setOrientation(LinearLayout.HORIZONTAL);
        Button startButton = actionButton("핀으로 이동 시작");
        startButton.setOnClickListener(v -> sendCommand(String.format(Locale.US, "NAV_START %.2f %.2f", selectedMapX, selectedMapY)));
        row2.addView(startButton, new LinearLayout.LayoutParams(0, dp(64), 1));

        Button stopButton = actionButton("이동 정지");
        stopButton.setOnClickListener(v -> sendCommand("NAV_STOP"));
        row2.addView(stopButton, new LinearLayout.LayoutParams(0, dp(64), 1));
        root.addView(row2);

        TextView safety = label("초음파는 충돌 방지 최우선, LiDAR는 지도/목표 방향, 카메라는 COCO 물체 종류 판단에 사용합니다.", 12, Color.rgb(82, 82, 91));
        safety.setPadding(0, dp(8), 0, dp(8));
        root.addView(safety);

        LinearLayout logButtons = new LinearLayout(this);
        logButtons.setOrientation(LinearLayout.HORIZONTAL);
        Button copyLogButton = actionButton("로그 복사");
        copyLogButton.setOnClickListener(v -> copyLogsToClipboard());
        logButtons.addView(copyLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        Button clearLogButton = actionButton("지우기");
        clearLogButton.setOnClickListener(v -> clearLogs());
        logButtons.addView(clearLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        root.addView(logButtons);

        ScrollView logScroll = new ScrollView(this);
        logText = label(logBuffer.toString(), 12, Color.rgb(63, 63, 70));
        logScroll.addView(logText);
        root.addView(logScroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(220)
        ));

        setContentView(scroll(root));
        startMapAutoScan();
    }

    private void updateMapGoalText() {
        if (mapGoalText != null) {
            mapGoalText.setText(String.format(Locale.US, "선택 목표: x=%.2fm, y=%.2fm", selectedMapX, selectedMapY));
        }
    }

    private void setMapViewMode(boolean use3d) {
        mapView3d = use3d;
        if (localMapView != null) {
            localMapView.setPerspectiveMode(mapView3d);
        }
        updateMapViewModeButtons();
    }

    private void updateMapViewModeButtons() {
        if (map2dButton != null) {
            map2dButton.setEnabled(mapView3d);
        }
        if (map3dButton != null) {
            map3dButton.setEnabled(!mapView3d);
        }
    }

    private void startMapAutoScan() {
        mapAutoScanEnabled = true;
        appendLog("지도 자동 갱신 시작: 0.1초 간격");
        mainHandler.removeCallbacks(mapAutoScanRunnable);
        mainHandler.post(mapAutoScanRunnable);
    }

    private void stopMapAutoScan() {
        mapAutoScanEnabled = false;
        mapScanInFlight = false;
        objectDetectInFlight = false;
        ultrasonicInFlight = false;
        mainHandler.removeCallbacks(mapAutoScanRunnable);
    }

    private void showManualScreen() {
        currentScreen = SCREEN_MANUAL;
        stopMapAutoScan();
        LinearLayout root = verticalRoot();
        root.addView(toolbar("수동 조작", true));

        mainStatusText = label("연결 안 됨", 18, Color.rgb(24, 24, 27));
        root.addView(mainStatusText);
        updateMainStatus();

        TextView description = label("좌/우는 현재 PWR 기준 90도 회전 후 정지, 후진은 오른쪽 180도 회전 후 전진합니다.", 13, Color.rgb(82, 82, 91));
        description.setPadding(0, dp(8), 0, dp(16));
        root.addView(description);

        manualSpeedText = label("", 16, Color.rgb(24, 24, 27));
        root.addView(manualSpeedText);

        SeekBar speedBar = new SeekBar(this);
        speedBar.setMax(255);
        speedBar.setProgress(manualSpeed());
        speedBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                updateManualSpeedText(progress);
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
                int speed = seekBar.getProgress();
                prefs.edit().putInt(PREF_MANUAL_SPEED, speed).apply();
                sendCommand("SPD " + speed);
            }
        });
        root.addView(speedBar, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));
        updateManualSpeedText(manualSpeed());

        Button forwardButton = actionButton("전진");
        forwardButton.setOnClickListener(v -> sendCommands("SPD " + manualSpeed(), "F"));
        root.addView(forwardButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        LinearLayout turnRow = new LinearLayout(this);
        turnRow.setOrientation(LinearLayout.HORIZONTAL);
        Button leftButton = actionButton("왼쪽");
        leftButton.setOnClickListener(v -> sendCommands("SPD " + manualSpeed(), "L"));
        turnRow.addView(leftButton, new LinearLayout.LayoutParams(0, dp(72), 1));

        Button stopButton = actionButton("정지");
        stopButton.setOnClickListener(v -> sendStopCommand());
        turnRow.addView(stopButton, new LinearLayout.LayoutParams(0, dp(72), 1));

        Button rightButton = actionButton("오른쪽");
        rightButton.setOnClickListener(v -> sendCommands("SPD " + manualSpeed(), "R"));
        turnRow.addView(rightButton, new LinearLayout.LayoutParams(0, dp(72), 1));
        root.addView(turnRow);

        Button backwardButton = actionButton("후진");
        backwardButton.setOnClickListener(v -> sendCommands("SPD " + manualSpeed(), "B"));
        root.addView(backwardButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button encoderButton = actionButton("엔코더");
        encoderButton.setOnClickListener(v -> sendCommand("ENC"));
        root.addView(encoderButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(56)
        ));

        LinearLayout logButtons = new LinearLayout(this);
        logButtons.setOrientation(LinearLayout.HORIZONTAL);
        Button copyLogButton = actionButton("로그 복사");
        copyLogButton.setOnClickListener(v -> copyLogsToClipboard());
        logButtons.addView(copyLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        Button clearLogButton = actionButton("지우기");
        clearLogButton.setOnClickListener(v -> clearLogs());
        logButtons.addView(clearLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        root.addView(logButtons);

        ScrollView logScroll = new ScrollView(this);
        logText = label(logBuffer.toString(), 12, Color.rgb(63, 63, 70));
        logScroll.addView(logText);
        root.addView(logScroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(220)
        ));

        setContentView(scroll(root));
    }

    private void showMiscScreen() {
        currentScreen = SCREEN_MISC;
        stopMapAutoScan();
        LinearLayout root = verticalRoot();
        root.addView(toolbar("커널 옵션", true));

        mainStatusText = label("연결 안 됨", 18, Color.rgb(24, 24, 27));
        root.addView(mainStatusText);
        updateMainStatus();

        TextView description = label("초음파 센서와 라즈베리파이 카메라 테스트", 13, Color.rgb(82, 82, 91));
        description.setPadding(0, dp(8), 0, dp(16));
        root.addView(description);

        kernelTokenInput = new EditText(this);
        kernelTokenInput.setHint("관리자 토큰");
        kernelTokenInput.setSingleLine(true);
        kernelTokenInput.setText("apptest");
        root.addView(kernelTokenInput, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(56)
        ));

        kernelCommandInput = new EditText(this);
        kernelCommandInput.setHint("Pi 명령어 입력 예: systemctl status robot-camera.service");
        kernelCommandInput.setSingleLine(false);
        kernelCommandInput.setMinLines(2);
        kernelCommandInput.setText("systemctl --no-pager --full status robot-camera.service");
        root.addView(kernelCommandInput, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(96)
        ));

        Button kernelExecButton = actionButton("커널 명령 실행");
        kernelExecButton.setOnClickListener(v -> sendKernelExecCommand());
        root.addView(kernelExecButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button kernelStatusButton = actionButton("Pi 상태 확인");
        kernelStatusButton.setOnClickListener(v -> sendCommand("KERNEL_STATUS"));
        root.addView(kernelStatusButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button arduinoPingButton = actionButton("Arduino 응답 확인");
        arduinoPingButton.setOnClickListener(v -> sendCommand("PING"));
        root.addView(arduinoPingButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button motorTestButton = actionButton("왼쪽 모터 1초 테스트");
        motorTestButton.setOnClickListener(v -> sendCommand("MOTOR_TEST"));
        root.addView(motorTestButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button kernelCleanButton = actionButton("로봇 서비스 정리");
        kernelCleanButton.setOnClickListener(v -> sendCommand("KERNEL_CLEAN_SERVICES"));
        root.addView(kernelCleanButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button disableOldButton = actionButton("기존 자동실행 끄기");
        disableOldButton.setOnClickListener(v -> sendCommand("KERNEL_DISABLE_OLD_AUTOSTART"));
        root.addView(disableOldButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button installAutostartButton = actionButton("현재 프로젝트 자동실행 설치");
        installAutostartButton.setOnClickListener(v -> sendCommand("KERNEL_INSTALL_AUTOSTART"));
        root.addView(installAutostartButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button kernelSafeStopButton = actionButton("관리자 안전 정지");
        kernelSafeStopButton.setOnClickListener(v -> sendCommand("KERNEL_SAFE_STOP"));
        root.addView(kernelSafeStopButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button kernelBluetoothButton = actionButton("블루투스 재시작");
        kernelBluetoothButton.setOnClickListener(v -> sendCommand("KERNEL_RESTART_BLUETOOTH"));
        root.addView(kernelBluetoothButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button ultrasonicButton = actionButton("초음파 거리 측정");
        ultrasonicButton.setOnClickListener(v -> sendCommand("US"));
        root.addView(ultrasonicButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        Button photoButton = actionButton("사진 테스트");
        photoButton.setOnClickListener(v -> requestPhoto());
        root.addView(photoButton, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(64)
        ));

        imageView = new ImageView(this);
        imageView.setAdjustViewBounds(true);
        imageView.setScaleType(ImageView.ScaleType.FIT_CENTER);
        imageView.setBackgroundColor(Color.rgb(244, 244, 245));
        root.addView(imageView, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(240)
        ));

        LinearLayout logButtons = new LinearLayout(this);
        logButtons.setOrientation(LinearLayout.HORIZONTAL);
        Button copyLogButton = actionButton("로그 복사");
        copyLogButton.setOnClickListener(v -> copyLogsToClipboard());
        logButtons.addView(copyLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        Button clearLogButton = actionButton("지우기");
        clearLogButton.setOnClickListener(v -> clearLogs());
        logButtons.addView(clearLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        root.addView(logButtons);

        ScrollView logScroll = new ScrollView(this);
        logText = label(logBuffer.toString(), 12, Color.rgb(63, 63, 70));
        logScroll.addView(logText);
        root.addView(logScroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(220)
        ));

        setContentView(scroll(root));
    }

    private int manualSpeed() {
        return prefs.getInt(PREF_MANUAL_SPEED, 160);
    }

    private void updateManualSpeedText(int speed) {
        if (manualSpeedText != null) {
            manualSpeedText.setText("속도 PWM: " + speed + " / 255");
        }
    }

    private void updateAutoSpeedText(int speed) {
        if (autoSpeedText != null) {
            autoSpeedText.setText("자율 속도 PWM: " + speed + " / 255");
        }
    }

    private void showBluetoothScreen() {
        currentScreen = SCREEN_BLUETOOTH;
        stopMapAutoScan();
        LinearLayout root = verticalRoot();
        root.addView(toolbar("블루투스", true));

        bluetoothStatusText = label("", 18, Color.rgb(24, 24, 27));
        root.addView(bluetoothStatusText);

        bluetoothFeatureSwitch = new Switch(this);
        bluetoothFeatureSwitch.setText("앱 블루투스 사용");
        bluetoothFeatureSwitch.setTextSize(15);
        bluetoothFeatureSwitch.setPadding(0, dp(12), 0, dp(12));
        bluetoothFeatureSwitch.setChecked(isBluetoothFeatureEnabled());
        bluetoothFeatureSwitch.setOnCheckedChangeListener(this::onBluetoothFeatureChanged);
        root.addView(bluetoothFeatureSwitch);

        LinearLayout scanRow = new LinearLayout(this);
        scanRow.setOrientation(LinearLayout.HORIZONTAL);
        scanRow.setGravity(Gravity.CENTER_VERTICAL);

        Button allSearchButton = actionButton("전체 검색");
        allSearchButton.setOnClickListener(v -> scanDevices());
        scanRow.addView(allSearchButton, new LinearLayout.LayoutParams(0, dp(56), 1));

        Button systemButton = actionButton("시스템 블루투스");
        systemButton.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)));
        scanRow.addView(systemButton, new LinearLayout.LayoutParams(0, dp(56), 1));
        root.addView(scanRow);

        scanStatusText = label("", 13, Color.rgb(82, 82, 91));
        root.addView(scanStatusText);

        deviceListContainer = new LinearLayout(this);
        deviceListContainer.setOrientation(LinearLayout.VERTICAL);
        deviceListContainer.setPadding(0, dp(8), 0, dp(8));
        root.addView(deviceListContainer);

        LinearLayout logButtons = new LinearLayout(this);
        logButtons.setOrientation(LinearLayout.HORIZONTAL);
        Button copyLogButton = actionButton("로그 복사");
        copyLogButton.setOnClickListener(v -> copyLogsToClipboard());
        logButtons.addView(copyLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        Button clearLogButton = actionButton("지우기");
        clearLogButton.setOnClickListener(v -> clearLogs());
        logButtons.addView(clearLogButton, new LinearLayout.LayoutParams(0, dp(52), 1));
        root.addView(logButtons);

        ScrollView logScroll = new ScrollView(this);
        logText = label(logBuffer.toString(), 12, Color.rgb(63, 63, 70));
        logScroll.addView(logText);
        root.addView(logScroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(200)
        ));

        setContentView(scroll(root));
        refreshBluetoothStatus(null);
        if (isBluetoothFeatureEnabled() && hasBluetoothPermission()) {
            loadPairedDevices();
        }
    }

    private LinearLayout toolbar(String title, boolean back) {
        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(0, 0, 0, dp(16));

        if (back) {
            Button backButton = actionButton("<");
            backButton.setOnClickListener(v -> showMainScreen());
            bar.addView(backButton, new LinearLayout.LayoutParams(dp(52), dp(52)));
        }

        TextView titleView = label(title, 22, Color.rgb(24, 24, 27));
        titleView.setGravity(Gravity.CENTER_VERTICAL);
        bar.addView(titleView, new LinearLayout.LayoutParams(0, dp(56), 1));

        if (!back) {
            ImageButton bluetoothButton = new ImageButton(this);
            bluetoothButton.setImageResource(getResources().getIdentifier("ic_bluetooth", "drawable", getPackageName()));
            bluetoothButton.setBackgroundColor(Color.TRANSPARENT);
            bluetoothButton.setContentDescription("블루투스");
            bluetoothButton.setPadding(dp(10), dp(10), dp(10), dp(10));
            bluetoothButton.setOnClickListener(v -> showBluetoothScreen());
            bar.addView(bluetoothButton, new LinearLayout.LayoutParams(dp(56), dp(56)));
        }
        return bar;
    }

    private LinearLayout verticalRoot() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(20), dp(20), dp(20), dp(20));
        return root;
    }

    private ScrollView scroll(View child) {
        ScrollView scrollView = new ScrollView(this);
        scrollView.addView(child);
        return scrollView;
    }

    private TextView label(String text, int sp, int color) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(sp);
        view.setTextColor(color);
        return view;
    }

    private Button actionButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(13);
        button.setAllCaps(false);
        return button;
    }

    private void onBluetoothFeatureChanged(CompoundButton button, boolean enabled) {
        prefs.edit().putBoolean(PREF_BT_FEATURE_ENABLED, enabled).apply();
        appendLog("앱 블루투스 설정 저장: " + (enabled ? "켜짐" : "꺼짐"));
        if (!enabled) {
            if (bluetoothAdapter != null && hasBluetoothPermission() && bluetoothAdapter.isDiscovering()) {
                bluetoothAdapter.cancelDiscovery();
            }
            devices.clear();
            expandedDevices.clear();
            rebuildDeviceList();
        }
        refreshBluetoothStatus(null);
        updateMainStatus();
    }

    private boolean isBluetoothFeatureEnabled() {
        return prefs.getBoolean(PREF_BT_FEATURE_ENABLED, true);
    }

    @SuppressLint("MissingPermission")
    private void loadPairedDevices() {
        if (!canUseBluetoothUi()) {
            return;
        }
        Set<BluetoothDevice> bondedDevices = bluetoothAdapter.getBondedDevices();
        for (BluetoothDevice device : bondedDevices) {
            addOrUpdateDevice(device);
        }
        appendLog("페어링된 기기 불러옴: " + bondedDevices.size());
        refreshBluetoothStatus(null);
    }

    @SuppressLint("MissingPermission")
    private void scanDevices() {
        if (!canUseBluetoothUi()) {
            return;
        }
        if (!bluetoothAdapter.isEnabled()) {
            refreshBluetoothStatus("휴대폰 블루투스가 꺼져 있습니다");
            startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS));
            return;
        }
        if (bluetoothAdapter.isDiscovering()) {
            bluetoothAdapter.cancelDiscovery();
        }
        devices.clear();
        expandedDevices.clear();
        rebuildDeviceList();
        loadPairedDevices();
        scanInProgress = bluetoothAdapter.startDiscovery();
        appendLog(scanInProgress ? "블루투스 전체 검색 시작" : "블루투스 전체 검색 실패");
        refreshBluetoothStatus(scanInProgress ? "검색 중..." : "검색 실패");
    }

    private boolean canUseBluetoothUi() {
        if (!isBluetoothFeatureEnabled()) {
            refreshBluetoothStatus("앱 블루투스 기능이 꺼져 있습니다");
            return false;
        }
        if (!hasBluetoothPermission()) {
            refreshBluetoothStatus("블루투스 권한이 필요합니다");
            requestBluetoothPermissions();
            return false;
        }
        if (bluetoothAdapter == null) {
            refreshBluetoothStatus("블루투스를 사용할 수 없습니다");
            return false;
        }
        return true;
    }

    @SuppressLint("MissingPermission")
    private void addOrUpdateDevice(BluetoothDevice device) {
        for (int i = 0; i < devices.size(); i++) {
            if (devices.get(i).getAddress().equals(device.getAddress())) {
                devices.set(i, device);
                rebuildDeviceList();
                return;
            }
        }
        devices.add(device);
        rebuildDeviceList();
    }

    private void rebuildDeviceList() {
        if (deviceListContainer == null) {
            return;
        }
        deviceListContainer.removeAllViews();
        if (devices.isEmpty()) {
            TextView empty = label("아직 검색된 블루투스 기기가 없습니다", 14, Color.rgb(113, 113, 122));
            empty.setPadding(0, dp(20), 0, dp(20));
            deviceListContainer.addView(empty);
            return;
        }
        for (BluetoothDevice device : devices) {
            deviceListContainer.addView(deviceRow(device));
        }
    }

    @SuppressLint("MissingPermission")
    private View deviceRow(BluetoothDevice device) {
        String mac = device.getAddress();
        boolean expanded = expandedDevices.contains(mac);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.VERTICAL);
        row.setPadding(dp(12), dp(10), dp(12), dp(10));
        row.setBackgroundColor(Color.rgb(248, 250, 252));

        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.HORIZONTAL);
        top.setGravity(Gravity.CENTER_VERTICAL);

        TextView name = label(safeDeviceName(device), 16, Color.rgb(24, 24, 27));
        name.setSingleLine(true);
        name.setEllipsize(TextUtils.TruncateAt.END);
        top.addView(name, new LinearLayout.LayoutParams(0, dp(34), 1));

        TextView state = label(isConnectedDevice(mac) ? "연결됨" : bondStateShort(device.getBondState()), 12,
                isConnectedDevice(mac) ? Color.rgb(22, 163, 74) : Color.rgb(82, 82, 91));
        state.setGravity(Gravity.CENTER_VERTICAL | Gravity.RIGHT);
        top.addView(state, new LinearLayout.LayoutParams(dp(92), dp(34)));

        Button connectButton = actionButton(isConnectedDevice(mac) ? "연결 해제" : "연결");
        connectButton.setOnClickListener(v -> {
            if (isConnectedDevice(mac)) {
                closeConnection();
                refreshBluetoothStatus("연결 안 됨");
                rebuildDeviceList();
            } else {
                beginPairOrConnect(device);
            }
        });
        top.addView(connectButton, new LinearLayout.LayoutParams(dp(110), dp(48)));
        row.addView(top);

        TextView address = label(mac, 12, Color.rgb(82, 82, 91));
        address.setSingleLine(true);
        address.setEllipsize(TextUtils.TruncateAt.END);
        row.addView(address);

        if (expanded) {
            TextView details = label("이름: " + safeDeviceName(device)
                    + "\n주소: " + mac
                    + "\n휴대폰 주소: " + localBluetoothAddress()
                    + "\n페어링: " + bondStateName(device.getBondState()), 13, Color.rgb(63, 63, 70));
            details.setPadding(0, dp(8), 0, 0);
            details.setMaxLines(5);
            details.setEllipsize(TextUtils.TruncateAt.END);
            row.addView(details);
        }

        row.setOnClickListener(v -> {
            if (expandedDevices.contains(mac)) {
                expandedDevices.remove(mac);
            } else {
                expandedDevices.add(mac);
            }
            rebuildDeviceList();
        });

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(0, 0, 0, dp(8));
        row.setLayoutParams(params);
        return row;
    }

    @SuppressLint("MissingPermission")
    private void beginPairOrConnect(BluetoothDevice device) {
        if (!canUseBluetoothUi()) {
            return;
        }
        if (bluetoothAdapter.isDiscovering()) {
            bluetoothAdapter.cancelDiscovery();
        }
        appendLog("사용자 연결 요청: " + describeDevice(device));
        if (device.getBondState() == BluetoothDevice.BOND_BONDED) {
            connectOnce(device.getAddress());
        } else if (device.getBondState() == BluetoothDevice.BOND_BONDING) {
            pendingConnectMac = device.getAddress();
            refreshBluetoothStatus("페어링 중...");
        } else {
            pendingConnectMac = device.getAddress();
            boolean started = device.createBond();
            appendLog("페어링 시작 결과=" + started);
            if (!started) {
                pendingConnectMac = null;
                connectOnce(device.getAddress());
            } else {
                refreshBluetoothStatus("페어링 중...");
            }
        }
    }

    private void connectOnce(String mac) {
        if (connectInProgress) {
            appendLog("이미 블루투스 연결을 시도 중입니다.");
            return;
        }
        connectInProgress = true;
        new Thread(() -> {
            try {
                closeConnection();
                connect(mac);
                mainHandler.post(() -> {
                    refreshBluetoothStatus("연결됨");
                    updateMainStatus();
                    rebuildDeviceList();
                });
            } catch (Exception exc) {
                appendLog("연결 실패: " + exc.getClass().getSimpleName() + ": " + exc.getMessage());
                closeConnection();
                mainHandler.post(() -> {
                    refreshBluetoothStatus("연결 실패: " + shortMessage(exc.getMessage()));
                    updateMainStatus();
                    rebuildDeviceList();
                });
            }
            finally {
                connectInProgress = false;
            }
        }, "BluetoothConnectOnce").start();
    }

    @SuppressLint("MissingPermission")
    private void connect(String mac) throws IOException {
        if (!hasBluetoothPermission()) {
            throw new IOException("블루투스 권한이 필요합니다");
        }
        if (bluetoothAdapter == null) {
            throw new IOException("블루투스를 사용할 수 없습니다");
        }
        BluetoothDevice device = bluetoothAdapter.getRemoteDevice(mac);
        refreshBluetoothStatus("연결 중...");
        appendLog("연결 대상: " + describeDevice(device));
        BluetoothSocket newSocket = connectUsingAvailableMethod(device);
        socket = newSocket;
        input = newSocket.getInputStream();
        output = newSocket.getOutputStream();
        connected = true;
        connectedMac = mac;
        appendLog("연결됨: 명령 전송 준비 완료");
    }

    @SuppressLint("MissingPermission")
    private BluetoothSocket connectUsingAvailableMethod(BluetoothDevice device) throws IOException {
        StringBuilder errors = new StringBuilder();
        ConnectAttempt[] attempts = new ConnectAttempt[]{
                new ConnectAttempt("insecure SPP UUID", () -> device.createInsecureRfcommSocketToServiceRecord(SPP_UUID)),
                new ConnectAttempt("SPP UUID", () -> device.createRfcommSocketToServiceRecord(SPP_UUID)),
                new ConnectAttempt("insecure RFCOMM channel 1", () -> createInsecureRfcommSocket(device, 1)),
                new ConnectAttempt("RFCOMM channel 1", () -> createRfcommSocket(device, 1))
        };
        for (ConnectAttempt attempt : attempts) {
            BluetoothSocket connectedSocket = tryConnect(attempt, errors);
            if (connectedSocket != null) {
                return connectedSocket;
            }
        }
        throw new IOException("모든 연결 방식 실패: " + shortMessage(errors.toString()));
    }

    private BluetoothSocket tryConnect(ConnectAttempt attempt, StringBuilder errors) {
        BluetoothSocket attemptSocket = null;
        try {
            appendLog("연결 방식 시도: " + attempt.name);
            attemptSocket = attempt.factory.create();
            if (bluetoothAdapter != null && hasBluetoothPermission()) {
                bluetoothAdapter.cancelDiscovery();
            }
            attemptSocket.connect();
            appendLog("연결 방식 성공: " + attempt.name);
            return attemptSocket;
        } catch (IOException exc) {
            closeSocketQuietly(attemptSocket);
            if (errors.length() > 0) {
                errors.append("; ");
            }
            errors.append(attempt.name).append(": ").append(exc.getMessage());
            appendLog("연결 방식 실패: " + attempt.name + ": " + exc.getMessage());
            sleep(150);
            return null;
        }
    }

    private BluetoothSocket createRfcommSocket(BluetoothDevice device, int channel) throws IOException {
        try {
            return (BluetoothSocket) device.getClass()
                    .getMethod("createRfcommSocket", int.class)
                    .invoke(device, channel);
        } catch (Exception exc) {
            throw new IOException("RFCOMM channel fallback 사용 불가", exc);
        }
    }

    private BluetoothSocket createInsecureRfcommSocket(BluetoothDevice device, int channel) throws IOException {
        try {
            return (BluetoothSocket) device.getClass()
                    .getMethod("createInsecureRfcommSocket", int.class)
                    .invoke(device, channel);
        } catch (Exception exc) {
            throw new IOException("Insecure RFCOMM channel fallback 사용 불가", exc);
        }
    }

    private interface SocketFactory {
        BluetoothSocket create() throws IOException;
    }

    private static class ConnectAttempt {
        final String name;
        final SocketFactory factory;

        ConnectAttempt(String name, SocketFactory factory) {
            this.name = name;
            this.factory = factory;
        }
    }

    private synchronized void sendCommand(String command) {
        sendCommands(command);
    }

    private void sendKernelExecCommand() {
        if (kernelTokenInput == null || kernelCommandInput == null) {
            return;
        }
        String token = kernelTokenInput.getText().toString().trim();
        String command = kernelCommandInput.getText().toString().trim();
        if (token.isEmpty() || command.isEmpty()) {
            Toast.makeText(this, "토큰과 명령어를 입력하세요", Toast.LENGTH_SHORT).show();
            return;
        }
        String token64 = Base64.encodeToString(token.getBytes(), Base64.NO_WRAP);
        String command64 = Base64.encodeToString(command.getBytes(), Base64.NO_WRAP);
        sendCommand("KERNEL_EXEC " + token64 + " " + command64);
    }

    private void requestMapScan(boolean logResponse) {
        if (!connected) {
            return;
        }
        if (mapScanInFlight) {
            return;
        }
        mapScanInFlight = true;
        new Thread(() -> {
            try {
                ensureConnected();
                synchronized (ioLock) {
                    writeLine("MAP_SCAN");
                    if (logResponse) {
                        appendLog("> MAP_SCAN");
                    }
                    String response = readLine(input);
                    if (logResponse) {
                        appendLog(response);
                    }
                    handleCommandResponse(response);
                }
            } catch (Exception exc) {
                if (logResponse || SCREEN_MAP.equals(currentScreen)) {
                    appendLog("지도 갱신 실패: " + exc.getMessage());
                }
                if (logResponse || SCREEN_MAP.equals(currentScreen)) {
                    markDisconnected();
                }
            } finally {
                mapScanInFlight = false;
            }
        }, "MapScan").start();
    }

    private void requestRealtimeCommand(String command, boolean logResponse) {
        if (!connected) {
            return;
        }
        if ("OBJECT_DETECT".equals(command)) {
            if (objectDetectInFlight) {
                return;
            }
            objectDetectInFlight = true;
        } else if ("US".equals(command)) {
            if (ultrasonicInFlight) {
                return;
            }
            ultrasonicInFlight = true;
        }
        new Thread(() -> {
            try {
                ensureConnected();
                synchronized (ioLock) {
                    writeLine(command);
                    if (logResponse) {
                        appendLog("> " + command);
                    }
                    String response = readLine(input);
                    if (logResponse || response.contains("\"error\"")) {
                        appendLog(response);
                    }
                    handleCommandResponse(response);
                }
            } catch (Exception exc) {
                if (logResponse || SCREEN_MAP.equals(currentScreen)) {
                    appendLog(command + " 갱신 실패: " + exc.getMessage());
                }
            } finally {
                if ("OBJECT_DETECT".equals(command)) {
                    objectDetectInFlight = false;
                } else if ("US".equals(command)) {
                    ultrasonicInFlight = false;
                }
            }
        }, "RealtimeCommand").start();
    }

    private synchronized void sendCommands(String... commands) {
        new Thread(() -> {
            try {
                ensureConnected();
                synchronized (ioLock) {
                    for (String command : commands) {
                        writeLine(command);
                        appendLog("> " + command);
                        String response = readLine(input);
                        appendLog(response);
                        handleCommandResponse(response);
                    }
                }
            } catch (Exception exc) {
                appendLog("전송 실패: " + exc.getMessage());
                markDisconnected();
            }
        }, "SendCommands").start();
    }

    private void sendStopCommand() {
        sendCommand("S");
    }

    private void handleCommandResponse(String response) {
        if (response == null || !response.contains("\"command\":\"map_scan\"") || !response.contains("\"ok\":true")) {
            return;
        }
        float[] bins = parseFloatArray(response, "\"bins_m\":[", "]");
        if (bins.length == 0) {
            return;
        }
        mainHandler.post(() -> {
            lidarBins = bins;
            if (localMapView != null) {
                localMapView.setLidarBins(lidarBins);
            }
        });
    }

    private float[] parseFloatArray(String text, String startMarker, String endMarker) {
        int start = text.indexOf(startMarker);
        if (start < 0) {
            return new float[0];
        }
        start += startMarker.length();
        int end = text.indexOf(endMarker, start);
        if (end < 0) {
            return new float[0];
        }
        String body = text.substring(start, end).trim();
        if (body.isEmpty()) {
            return new float[0];
        }
        String[] parts = body.split(",");
        float[] values = new float[parts.length];
        for (int i = 0; i < parts.length; i++) {
            try {
                values[i] = Float.parseFloat(parts[i].trim());
            } catch (NumberFormatException exc) {
                values[i] = -1.0f;
            }
        }
        return values;
    }

    private synchronized void requestPhoto() {
        new Thread(() -> {
            try {
                ensureConnected();
                byte[] jpeg;
                synchronized (ioLock) {
                    writeLine("PHOTO");
                    appendLog("> PHOTO");
                    String header = readLine(input);
                    appendLog(header);
                    if (!header.startsWith("JPEG ")) {
                        throw new IOException("예상하지 못한 사진 헤더: " + header);
                    }
                    int length = Integer.parseInt(header.substring(5).trim());
                    jpeg = readExact(input, length);
                }
                Bitmap bitmap = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.length);
                if (bitmap == null) {
                    throw new IOException("JPEG 해석 실패, bytes=" + jpeg.length);
                }
                File savedPhoto = savePhoto(jpeg);
                appendLog("사진 수신: bytes=" + jpeg.length
                        + ", 해상도=" + bitmap.getWidth() + "x" + bitmap.getHeight()
                        + ", 저장=" + savedPhoto.getAbsolutePath());
                mainHandler.post(() -> {
                    if (imageView != null) {
                        imageView.setImageBitmap(bitmap);
                    }
                    updateMainStatusText("사진 수신: " + bitmap.getWidth() + "x" + bitmap.getHeight());
                });
            } catch (Exception exc) {
                appendLog("사진 실패: " + exc.getMessage());
                markDisconnected();
            }
        }, "PhotoRequest").start();
    }

    private File savePhoto(byte[] jpeg) throws IOException {
        File directory = getExternalFilesDir("Pictures");
        if (directory == null) {
            directory = getFilesDir();
        }
        if (!directory.exists() && !directory.mkdirs()) {
            throw new IOException("사진 저장 폴더를 사용할 수 없음: " + directory.getAbsolutePath());
        }
        String timestamp = new SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.US).format(new Date());
        File photoFile = new File(directory, "robot_photo_" + timestamp + ".jpg");
        try (FileOutputStream stream = new FileOutputStream(photoFile)) {
            stream.write(jpeg);
        }
        return photoFile;
    }

    private void ensureConnected() throws IOException {
        if (!connected || socket == null || output == null || input == null) {
            throw new IOException("연결되어 있지 않습니다");
        }
    }

    private void writeLine(String text) throws IOException {
        output.write((text + "\n").getBytes());
        output.flush();
    }

    private String readLine(InputStream stream) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        while (true) {
            int value = stream.read();
            if (value < 0) {
                throw new IOException("연결 안 됨");
            }
            if (value == '\n' || value == '\r') {
                if (buffer.size() > 0) {
                    return buffer.toString("UTF-8").trim();
                }
                continue;
            }
            buffer.write(value);
            if (buffer.size() > 4096) {
                throw new IOException("Line too long");
            }
        }
    }

    private byte[] readExact(InputStream stream, int length) throws IOException {
        byte[] data = new byte[length];
        int offset = 0;
        while (offset < length) {
            int read = stream.read(data, offset, length - offset);
            if (read < 0) {
                throw new IOException("연결 안 됨 during image read");
            }
            offset += read;
        }
        return data;
    }

    private void closeConnection() {
        try {
            if (socket != null) {
                socket.close();
            }
        } catch (Exception ignored) {
        }
        socket = null;
        input = null;
        output = null;
        connected = false;
        connectedMac = null;
    }

    private void closeSocketQuietly(BluetoothSocket socketToClose) {
        if (socketToClose == null) {
            return;
        }
        try {
            socketToClose.close();
        } catch (Exception ignored) {
        }
    }

    private void markDisconnected() {
        closeConnection();
        mainHandler.post(() -> {
            refreshBluetoothStatus("연결 안 됨");
            updateMainStatus();
            rebuildDeviceList();
        });
    }

    private void requestBluetoothPermissions() {
        if (Build.VERSION.SDK_INT >= 31) {
            if (!hasBluetoothPermission()) {
                requestPermissions(new String[]{
                        Manifest.permission.BLUETOOTH_CONNECT,
                        Manifest.permission.BLUETOOTH_SCAN
                }, 10);
            }
        } else if (Build.VERSION.SDK_INT >= 23) {
            if (!hasBluetoothPermission()) {
                requestPermissions(new String[]{
                        Manifest.permission.ACCESS_FINE_LOCATION
                }, 10);
            }
        }
    }

    private boolean hasBluetoothPermission() {
        if (Build.VERSION.SDK_INT >= 31) {
            return checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
                    && checkSelfPermission(Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED;
        }
        if (Build.VERSION.SDK_INT >= 23) {
            return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        }
        return true;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        appendLog("권한 결과: 허용=" + hasBluetoothPermission());
        refreshBluetoothStatus(null);
        if (SCREEN_BLUETOOTH.equals(currentScreen) && hasBluetoothPermission()) {
            loadPairedDevices();
        }
    }

    private void refreshBluetoothStatus(String override) {
        String status;
        if (override != null) {
            status = override;
        } else if (!isBluetoothFeatureEnabled()) {
            status = "앱 블루투스 기능: 꺼짐";
        } else if (bluetoothAdapter == null) {
            status = "블루투스를 사용할 수 없습니다";
        } else if (!hasBluetoothPermission()) {
            status = "블루투스 권한이 필요합니다";
        } else if (!bluetoothAdapter.isEnabled()) {
            status = "휴대폰 블루투스: 꺼짐";
        } else if (connected) {
            status = "연결됨: " + connectedMac;
        } else if (scanInProgress) {
            status = "검색 중...";
        } else {
            status = "준비됨: 전체 검색 후 연결을 누르세요.";
        }
        if (bluetoothStatusText != null) {
            bluetoothStatusText.setText(status);
        }
        if (scanStatusText != null) {
            scanStatusText.setText("기기 수: " + devices.size() + "  휴대폰 주소: " + localBluetoothAddress());
        }
    }

    private void updateMainStatus() {
        if (connected) {
            updateMainStatusText("연결됨: " + connectedMac);
        } else {
            updateMainStatusText("연결 안 됨");
        }
    }

    private void updateMainStatusText(String text) {
        if (mainStatusText != null) {
            mainStatusText.setText(text);
        }
    }

    @SuppressLint("MissingPermission")
    private String describeDevice(BluetoothDevice device) {
        return safeDeviceName(device) + " " + device.getAddress()
                + " " + bondStateName(device.getBondState());
    }

    @SuppressLint("MissingPermission")
    private String safeDeviceName(BluetoothDevice device) {
        try {
            String name = device.getName();
            if (name == null || name.trim().isEmpty()) {
                return "(이름 없음)";
            }
            return name;
        } catch (SecurityException exc) {
            return "(이름 권한 없음)";
        }
    }

    private boolean isConnectedDevice(String mac) {
        return connected && mac != null && mac.equals(connectedMac);
    }

    @SuppressLint("MissingPermission")
    private String localBluetoothAddress() {
        try {
            if (bluetoothAdapter == null || !hasBluetoothPermission()) {
                return "사용 불가";
            }
            String address = bluetoothAdapter.getAddress();
            return address == null ? "알 수 없음" : address;
        } catch (Exception exc) {
            return "숨김";
        }
    }

    private String bondStateName(int state) {
        if (state == BluetoothDevice.BOND_BONDED) {
            return "페어링됨";
        }
        if (state == BluetoothDevice.BOND_BONDING) {
            return "페어링 중";
        }
        if (state == BluetoothDevice.BOND_NONE) {
            return "페어링 안 됨";
        }
        return "페어링 알 수 없음(" + state + ")";
    }

    private String bondStateShort(int state) {
        if (state == BluetoothDevice.BOND_BONDED) {
            return "페어링됨";
        }
        if (state == BluetoothDevice.BOND_BONDING) {
            return "페어링 중";
        }
        return "새 기기";
    }

    private String adapterStateName(int state) {
        if (state == BluetoothAdapter.STATE_ON) {
            return "켜짐";
        }
        if (state == BluetoothAdapter.STATE_OFF) {
            return "꺼짐";
        }
        if (state == BluetoothAdapter.STATE_TURNING_ON) {
            return "켜지는 중";
        }
        if (state == BluetoothAdapter.STATE_TURNING_OFF) {
            return "꺼지는 중";
        }
        return "알 수 없음(" + state + ")";
    }

    private String shortMessage(String text) {
        if (text == null) {
            return "";
        }
        return text.length() <= 160 ? text : text.substring(0, 160) + "...";
    }

    private void copyLogsToClipboard() {
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard == null) {
            Toast.makeText(this, "클립보드를 사용할 수 없습니다", Toast.LENGTH_SHORT).show();
            return;
        }
        clipboard.setPrimaryClip(ClipData.newPlainText("로봇 블루투스 로그", logBuffer.toString()));
        Toast.makeText(this, "로그를 복사했습니다", Toast.LENGTH_SHORT).show();
    }

    private void clearLogs() {
        logBuffer.setLength(0);
        if (logText != null) {
            logText.setText("");
        }
        appendLog("로그를 지웠습니다");
    }

    private void appendLog(String text) {
        Log.d(TAG, text);
        mainHandler.post(() -> {
            String line = logTimeFormat.format(new Date()) + " " + text + "\n";
            logBuffer.append(line);
            if (logText != null) {
                logText.append(line);
            }
        });
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private class LocalMapView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private float goalX = 0.0f;
        private float goalY = 1.0f;
        private float[] bins = new float[0];
        private boolean perspectiveMode = false;

        LocalMapView(Context context) {
            super(context);
            setBackgroundColor(Color.rgb(248, 250, 252));
        }

        void setGoal(float x, float y) {
            goalX = x;
            goalY = y;
            invalidate();
        }

        void setLidarBins(float[] lidarBins) {
            bins = lidarBins == null ? new float[0] : lidarBins;
            invalidate();
        }

        void setPerspectiveMode(boolean usePerspective) {
            perspectiveMode = usePerspective;
            invalidate();
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int w = getWidth();
            int h = getHeight();
            if (perspectiveMode) {
                drawPerspectiveMap(canvas, w, h);
                return;
            }
            float cx = w / 2.0f;
            float cy = h / 2.0f;
            float scale = Math.min(w, h) / 5.0f;

            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(1);
            paint.setColor(Color.rgb(203, 213, 225));
            for (int i = -2; i <= 2; i++) {
                canvas.drawLine(cx + i * scale, 0, cx + i * scale, h, paint);
                canvas.drawLine(0, cy + i * scale, w, cy + i * scale, paint);
            }

            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.rgb(37, 99, 235));
            canvas.drawCircle(cx, cy, dp(8), paint);

            if (bins.length > 0) {
                paint.setColor(Color.rgb(15, 118, 110));
                for (int i = 0; i < bins.length; i++) {
                    float distance = bins[i];
                    if (distance <= 0.0f) {
                        continue;
                    }
                    float clamped = Math.min(distance, 2.4f);
                    double angleRad = Math.toRadians(i * (360.0 / bins.length));
                    float px = cx + (float) Math.sin(angleRad) * clamped * scale;
                    float py = cy - (float) Math.cos(angleRad) * clamped * scale;
                    canvas.drawCircle(px, py, dp(4), paint);
                }
            }

            float gx = cx + goalX * scale;
            float gy = cy - goalY * scale;
            paint.setColor(Color.rgb(220, 38, 38));
            canvas.drawCircle(gx, gy, dp(9), paint);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(dp(2));
            canvas.drawLine(cx, cy, gx, gy, paint);

            paint.setStyle(Paint.Style.FILL);
            paint.setTextSize(dp(12));
            paint.setColor(Color.rgb(63, 63, 70));
            canvas.drawText("로봇", cx + dp(10), cy - dp(10), paint);
            canvas.drawText("목표", gx + dp(10), gy - dp(10), paint);
        }

        private void drawPerspectiveMap(Canvas canvas, int w, int h) {
            float cx = w / 2.0f;
            float baseY = h * 0.82f;
            float horizonY = h * 0.22f;
            float maxDistance = 5.0f;

            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.rgb(248, 250, 252));
            canvas.drawRect(0, 0, w, h, paint);

            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(1);
            paint.setColor(Color.rgb(203, 213, 225));
            for (int i = -4; i <= 4; i++) {
                canvas.drawLine(cx, baseY, cx + i * w / 8.0f, horizonY, paint);
            }
            for (int i = 1; i <= 5; i++) {
                float t = i / 5.0f;
                float y = baseY - (baseY - horizonY) * t;
                float half = w * (1.0f - t) * 0.5f;
                canvas.drawLine(cx - half, y, cx + half, y, paint);
            }

            if (bins.length > 0) {
                paint.setStyle(Paint.Style.FILL);
                for (int i = 0; i < bins.length; i++) {
                    float distance = bins[i];
                    if (distance <= 0.0f) {
                        continue;
                    }
                    double angleRad = Math.toRadians(i * (360.0 / bins.length));
                    float forward = (float) Math.cos(angleRad) * distance;
                    if (forward < -0.3f) {
                        continue;
                    }
                    float side = (float) Math.sin(angleRad) * distance;
                    float depth = Math.max(0.0f, Math.min(maxDistance, forward + 0.6f)) / maxDistance;
                    float y = baseY - (baseY - horizonY) * depth;
                    float widthAtDepth = w * (1.0f - depth * 0.78f);
                    float x = cx + side / maxDistance * widthAtDepth;
                    float radius = dp(7) * (1.0f - depth * 0.55f);
                    paint.setColor(Color.rgb(15, 118, 110));
                    canvas.drawCircle(x, y, Math.max(dp(2), radius), paint);
                }
            }

            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.rgb(37, 99, 235));
            canvas.drawCircle(cx, baseY, dp(9), paint);
            paint.setTextSize(dp(12));
            paint.setColor(Color.rgb(63, 63, 70));
            canvas.drawText("로봇", cx + dp(10), baseY - dp(10), paint);
            canvas.drawText("3D 보기: 2D LiDAR 원근 시각화", dp(12), dp(24), paint);
        }

        @Override
        public boolean onTouchEvent(MotionEvent event) {
            if (event.getAction() != MotionEvent.ACTION_DOWN && event.getAction() != MotionEvent.ACTION_MOVE) {
                return true;
            }
            float scale = Math.min(getWidth(), getHeight()) / 5.0f;
            selectedMapX = (event.getX() - getWidth() / 2.0f) / scale;
            selectedMapY = (getHeight() / 2.0f - event.getY()) / scale;
            selectedMapX = Math.max(-2.4f, Math.min(2.4f, selectedMapX));
            selectedMapY = Math.max(-2.4f, Math.min(2.4f, selectedMapY));
            setGoal(selectedMapX, selectedMapY);
            updateMapGoalText();
            return true;
        }
    }

    private void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ignored) {
        }
    }
}
