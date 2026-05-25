const uint8_t LEFT_N1 = 5;
const uint8_t LEFT_N2 = 6;
const uint8_t RIGHT_N3 = 8;
const uint8_t RIGHT_N4 = 9;
const uint8_t ENC_A = 2;
const uint8_t ENC_B = 3;

const uint8_t US_LEFT_TRIG = 22;
const uint8_t US_LEFT_ECHO = 23;
const uint8_t US_FRONT_TRIG = 24;
const uint8_t US_FRONT_ECHO = 25;
const uint8_t US_RIGHT_TRIG = 26;
const uint8_t US_RIGHT_ECHO = 27;

const uint8_t DEFAULT_SPEED = 160;
const unsigned long COMMAND_TIMEOUT_MS = 5000;
const unsigned long ULTRASONIC_TIMEOUT_US = 30000UL;
const unsigned long AUTO_SAMPLE_MS = 140;
const unsigned long AUTO_TURN_MS = 350;
const unsigned long AUTO_BACK_MS = 250;
const unsigned long AUTO_NUDGE_MS = 220;
const unsigned long TURN_90_MS_AT_SPEED = 650;
const uint8_t TURN_CALIBRATION_SPEED = 171;

const float AUTO_CLEAR_CM = 40.0;
const float AUTO_TOO_CLOSE_CM = 15.0;
const float AUTO_SIDE_CLEAR_CM = 30.0;
const float ULTRASONIC_NO_ECHO_AS_FAR_CM = 400.0;

volatile long encoderCount = 0;
uint8_t motorSpeed = DEFAULT_SPEED;
unsigned long lastCommandAt = 0;
unsigned long lastAutoSampleAt = 0;
unsigned long autoActionUntil = 0;
bool autoMode = false;
const char* autoState = "off";
String lineBuffer = "";

void readCommands();
void handleCommand(String command);
void forwardMotor();
void backwardMotor();
void turnLeft();
void turnRight();
void turnLeft90();
void turnRight90();
void turnRight180AndForward();
void steerLeft();
void steerRight();
void nudgeLeft();
void nudgeRight();
unsigned long calibratedTurn90Ms();
void stopMotor();
void driveLeftForward();
void driveLeftBackward();
void stopLeft();
void driveRightForward();
void driveRightBackward();
void stopRight();
void runAutonomous();
void setAutoMode(bool enabled);
void onEncoderA();
float readUltrasonicCm(uint8_t trigPin, uint8_t echoPin);
float sideDistanceOrFar(float distanceCm);
void printStatus(const char* command);
void printUltrasonic();
void printAutoStatus();
void printMotorTestPhase(const char* phase);

void setup() {
  Serial.begin(115200);

  pinMode(LEFT_N1, OUTPUT);
  pinMode(LEFT_N2, OUTPUT);
  pinMode(RIGHT_N3, OUTPUT);
  pinMode(RIGHT_N4, OUTPUT);
  pinMode(ENC_A, INPUT_PULLUP);
  pinMode(ENC_B, INPUT_PULLUP);
  pinMode(US_LEFT_TRIG, OUTPUT);
  pinMode(US_LEFT_ECHO, INPUT);
  pinMode(US_FRONT_TRIG, OUTPUT);
  pinMode(US_FRONT_ECHO, INPUT);
  pinMode(US_RIGHT_TRIG, OUTPUT);
  pinMode(US_RIGHT_ECHO, INPUT);

  digitalWrite(US_LEFT_TRIG, LOW);
  digitalWrite(US_FRONT_TRIG, LOW);
  digitalWrite(US_RIGHT_TRIG, LOW);
  attachInterrupt(digitalPinToInterrupt(ENC_A), onEncoderA, CHANGE);

  stopMotor();
  lastCommandAt = millis();

  Serial.println("{\"motor_bridge\":\"ready\",\"leftN1\":5,\"leftN2\":6,\"rightN3\":8,\"rightN4\":9,\"encA\":2,\"encB\":3,\"ultraLeft\":[22,23],\"ultraFront\":[24,25],\"ultraRight\":[26,27]}");
}

void loop() {
  readCommands();

  if (autoMode) {
    runAutonomous();
  } else if (millis() - lastCommandAt > COMMAND_TIMEOUT_MS) {
    stopMotor();
  }
}

void readCommands() {
  while (Serial.available() > 0) {
    char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (lineBuffer.length() > 0) {
        handleCommand(lineBuffer);
        lineBuffer = "";
      }
    } else if (lineBuffer.length() < 32) {
      lineBuffer += ch;
    }
  }
}

void handleCommand(String command) {
  command.trim();
  command.toUpperCase();
  lastCommandAt = millis();

  if (command == "PING") {
    printStatus("ping");
    return;
  }
  if (command == "MOTOR_STATUS") {
    printStatus("motor_status");
    return;
  }
  if (command == "LEFTF") {
    autoMode = false;
    autoState = "off";
    driveLeftForward();
    printStatus("left_forward");
    return;
  }
  if (command == "LEFTB") {
    autoMode = false;
    autoState = "off";
    driveLeftBackward();
    printStatus("left_backward");
    return;
  }
  if (command == "RIGHTF") {
    autoMode = false;
    autoState = "off";
    driveRightForward();
    printStatus("right_forward");
    return;
  }
  if (command == "RIGHTB") {
    autoMode = false;
    autoState = "off";
    driveRightBackward();
    printStatus("right_backward");
    return;
  }
  if (command == "MOTOR_TEST") {
    autoMode = false;
    autoState = "off";
    uint8_t oldSpeed = motorSpeed;
    if (motorSpeed < 170) {
      motorSpeed = 170;
    }
    printMotorTestPhase("left_forward_start");
    driveLeftForward();
    delay(1200);
    stopMotor();
    printMotorTestPhase("left_forward_stop");
    motorSpeed = oldSpeed;
    return;
  }

  if (command == "F") {
    autoMode = false;
    autoState = "off";
    forwardMotor();
    printStatus("forward");
    return;
  }
  if (command == "B") {
    autoMode = false;
    autoState = "off";
    turnRight180AndForward();
    printStatus("turn_180_forward");
    return;
  }
  if (command == "L") {
    autoMode = false;
    autoState = "off";
    turnLeft90();
    printStatus("left_90");
    return;
  }
  if (command == "R") {
    autoMode = false;
    autoState = "off";
    turnRight90();
    printStatus("right_90");
    return;
  }
  if (command == "NUDGE_L") {
    autoMode = false;
    autoState = "off";
    nudgeLeft();
    printStatus("nudge_left");
    return;
  }
  if (command == "NUDGE_R") {
    autoMode = false;
    autoState = "off";
    nudgeRight();
    printStatus("nudge_right");
    return;
  }
  if (command == "STEER_L") {
    autoMode = false;
    autoState = "off";
    steerLeft();
    printStatus("steer_left");
    return;
  }
  if (command == "STEER_R") {
    autoMode = false;
    autoState = "off";
    steerRight();
    printStatus("steer_right");
    return;
  }
  if (command == "S") {
    autoMode = false;
    autoState = "off";
    stopMotor();
    printStatus("stop");
    return;
  }
  if (command.startsWith("SPD ")) {
    int value = command.substring(4).toInt();
    motorSpeed = constrain(value, 0, 255);
    printStatus("speed");
    return;
  }
  if (command == "ENC") {
    printStatus("encoder");
    return;
  }
  if (command == "US" || command == "DIST" || command == "ULTRA") {
    printUltrasonic();
    return;
  }
  if (command == "AUTO_ON") {
    setAutoMode(true);
    printAutoStatus();
    return;
  }
  if (command == "AUTO_OFF") {
    setAutoMode(false);
    printAutoStatus();
    return;
  }
  if (command == "AUTO_STATUS") {
    printAutoStatus();
    return;
  }

  stopMotor();
  Serial.println("{\"error\":\"unknown_command\"}");
}

void forwardMotor() {
  driveLeftForward();
  driveRightForward();
}

void backwardMotor() {
  driveLeftBackward();
  driveRightBackward();
}

void turnLeft() {
  stopLeft();
  driveRightForward();
}

void turnRight() {
  driveLeftForward();
  stopRight();
}

void turnLeft90() {
  unsigned long turnMs = calibratedTurn90Ms();
  turnLeft();
  delay(turnMs);
  stopMotor();
  lastCommandAt = millis();
}

void turnRight90() {
  unsigned long turnMs = calibratedTurn90Ms();
  turnRight();
  delay(turnMs);
  stopMotor();
  lastCommandAt = millis();
}

void turnRight180AndForward() {
  unsigned long turnMs = calibratedTurn90Ms() * 2;
  turnRight();
  delay(turnMs);
  forwardMotor();
  lastCommandAt = millis();
}

void steerLeft() {
  turnLeft();
  lastCommandAt = millis();
}

void steerRight() {
  turnRight();
  lastCommandAt = millis();
}

void nudgeLeft() {
  uint8_t oldSpeed = motorSpeed;
  if (motorSpeed < 120) {
    motorSpeed = 120;
  }
  turnLeft();
  delay(AUTO_NUDGE_MS);
  stopMotor();
  motorSpeed = oldSpeed;
  lastCommandAt = millis();
}

void nudgeRight() {
  uint8_t oldSpeed = motorSpeed;
  if (motorSpeed < 120) {
    motorSpeed = 120;
  }
  turnRight();
  delay(AUTO_NUDGE_MS);
  stopMotor();
  motorSpeed = oldSpeed;
  lastCommandAt = millis();
}

unsigned long calibratedTurn90Ms() {
  uint8_t safeSpeed = motorSpeed < 1 ? 1 : motorSpeed;
  unsigned long adjusted = (TURN_90_MS_AT_SPEED * (unsigned long)TURN_CALIBRATION_SPEED) / safeSpeed;
  return constrain(adjusted, 350UL, 1800UL);
}

void stopMotor() {
  stopLeft();
  stopRight();
}

void driveLeftForward() {
  analogWrite(LEFT_N1, 0);
  analogWrite(LEFT_N2, motorSpeed);
}

void driveLeftBackward() {
  analogWrite(LEFT_N1, motorSpeed);
  analogWrite(LEFT_N2, 0);
}

void stopLeft() {
  analogWrite(LEFT_N1, 0);
  analogWrite(LEFT_N2, 0);
}

void driveRightForward() {
  analogWrite(RIGHT_N3, 0);
  analogWrite(RIGHT_N4, motorSpeed);
}

void driveRightBackward() {
  analogWrite(RIGHT_N3, motorSpeed);
  analogWrite(RIGHT_N4, 0);
}

void stopRight() {
  analogWrite(RIGHT_N3, 0);
  analogWrite(RIGHT_N4, 0);
}

void runAutonomous() {
  unsigned long now = millis();
  if (now < autoActionUntil) {
    return;
  }
  if (now - lastAutoSampleAt < AUTO_SAMPLE_MS) {
    return;
  }
  lastAutoSampleAt = now;

  float leftCm = readUltrasonicCm(US_LEFT_TRIG, US_LEFT_ECHO);
  delay(35);
  float frontCm = readUltrasonicCm(US_FRONT_TRIG, US_FRONT_ECHO);
  delay(35);
  float rightCm = readUltrasonicCm(US_RIGHT_TRIG, US_RIGHT_ECHO);

  if (frontCm < 0) {
    frontCm = ULTRASONIC_NO_ECHO_AS_FAR_CM;
  }
  if (frontCm <= AUTO_TOO_CLOSE_CM) {
    backwardMotor();
    autoState = "back";
    autoActionUntil = now + AUTO_BACK_MS;
    return;
  }
  if (frontCm <= AUTO_CLEAR_CM) {
    float safeLeftCm = sideDistanceOrFar(leftCm);
    float safeRightCm = sideDistanceOrFar(rightCm);
    if (safeLeftCm >= AUTO_SIDE_CLEAR_CM || safeRightCm >= AUTO_SIDE_CLEAR_CM) {
      if (safeLeftCm > safeRightCm) {
        turnLeft();
        autoState = "avoid_left";
      } else {
        turnRight();
        autoState = "avoid_right";
      }
    } else {
      backwardMotor();
      autoState = "blocked_back";
      autoActionUntil = now + AUTO_BACK_MS;
      return;
    }
    autoActionUntil = now + AUTO_TURN_MS;
    return;
  }

  forwardMotor();
  autoState = "forward";
}

void setAutoMode(bool enabled) {
  autoMode = enabled;
  lastCommandAt = millis();
  lastAutoSampleAt = 0;
  autoActionUntil = 0;
  if (enabled) {
    autoState = "starting";
  } else {
    autoState = "off";
    stopMotor();
  }
}

void onEncoderA() {
  int a = digitalRead(ENC_A);
  int b = digitalRead(ENC_B);
  if (a == b) {
    encoderCount++;
  } else {
    encoderCount--;
  }
}

float readUltrasonicCm(uint8_t trigPin, uint8_t echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  unsigned long duration = pulseIn(echoPin, HIGH, ULTRASONIC_TIMEOUT_US);
  if (duration == 0) {
    return -1.0;
  }
  return duration / 58.0;
}

float sideDistanceOrFar(float distanceCm) {
  if (distanceCm < 0) {
    return ULTRASONIC_NO_ECHO_AS_FAR_CM;
  }
  return distanceCm;
}

void printStatus(const char* command) {
  Serial.print("{\"command\":\"");
  Serial.print(command);
  Serial.print("\",\"speed\":");
  Serial.print(motorSpeed);
  Serial.print(",\"auto\":");
  Serial.print(autoMode ? "true" : "false");
  Serial.print(",\"encoder\":");
  Serial.print(encoderCount);
  Serial.println("}");
}

void printUltrasonic() {
  float leftCm = readUltrasonicCm(US_LEFT_TRIG, US_LEFT_ECHO);
  delay(35);
  float frontCm = readUltrasonicCm(US_FRONT_TRIG, US_FRONT_ECHO);
  delay(35);
  float rightCm = readUltrasonicCm(US_RIGHT_TRIG, US_RIGHT_ECHO);

  Serial.print("{\"command\":\"ultrasonic\",\"left_cm\":");
  Serial.print(leftCm, 1);
  Serial.print(",\"front_cm\":");
  Serial.print(frontCm, 1);
  Serial.print(",\"right_cm\":");
  Serial.print(rightCm, 1);
  Serial.print(",\"encoder\":");
  Serial.print(encoderCount);
  Serial.println("}");
}

void printAutoStatus() {
  float leftCm = readUltrasonicCm(US_LEFT_TRIG, US_LEFT_ECHO);
  delay(35);
  float frontCm = readUltrasonicCm(US_FRONT_TRIG, US_FRONT_ECHO);
  delay(35);
  float rightCm = readUltrasonicCm(US_RIGHT_TRIG, US_RIGHT_ECHO);

  Serial.print("{\"command\":\"auto_status\",\"auto\":");
  Serial.print(autoMode ? "true" : "false");
  Serial.print(",\"state\":\"");
  Serial.print(autoState);
  Serial.print("\",\"speed\":");
  Serial.print(motorSpeed);
  Serial.print(",\"left_cm\":");
  Serial.print(leftCm, 1);
  Serial.print(",\"front_cm\":");
  Serial.print(frontCm, 1);
  Serial.print(",\"right_cm\":");
  Serial.print(rightCm, 1);
  Serial.print(",\"clear_cm\":");
  Serial.print(AUTO_CLEAR_CM, 1);
  Serial.print(",\"side_clear_cm\":");
  Serial.print(AUTO_SIDE_CLEAR_CM, 1);
  Serial.print(",\"too_close_cm\":");
  Serial.print(AUTO_TOO_CLOSE_CM, 1);
  Serial.print(",\"encoder\":");
  Serial.print(encoderCount);
  Serial.println("}");
}

void printMotorTestPhase(const char* phase) {
  Serial.print("{\"command\":\"motor_test\",\"phase\":\"");
  Serial.print(phase);
  Serial.print("\",\"speed\":");
  Serial.print(motorSpeed);
  Serial.print(",\"leftN1\":");
  Serial.print(LEFT_N1);
  Serial.print(",\"leftN2\":");
  Serial.print(LEFT_N2);
  Serial.print(",\"rightN3\":");
  Serial.print(RIGHT_N3);
  Serial.print(",\"rightN4\":");
  Serial.print(RIGHT_N4);
  Serial.print(",\"encoder\":");
  Serial.print(encoderCount);
  Serial.println("}");
}
