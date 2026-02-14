#include <Adafruit_NeoPixel.h>
#include <WiFi.h>
#include <time.h>
#include <cstring>
#include "CYOBot_NeoPixel.h"

#define LED_PIN NEO_BRAIN

constexpr char WIFI_SSID[] = "NHA PINK";
constexpr char WIFI_PASSWORD[] = "pinkpink";
constexpr char NTP_SERVER[] = "pool.ntp.org";
constexpr long GMT_OFFSET_SEC = 7 * 3600;   // UTC+7
constexpr int DAYLIGHT_OFFSET_SEC = 0;
constexpr uint32_t WIFI_CONNECT_TIMEOUT_MS = 15000;

constexpr uint32_t DISPLAY_INTERVAL_MS = 1000;
constexpr uint32_t BUTTON_DEBOUNCE_MS = 40;
constexpr uint32_t TIME_SCROLL_INTERVAL_MS = 150;
constexpr uint8_t DISPLAY_WIDTH = 5;
constexpr uint8_t CHAR_WIDTH = 5;
constexpr uint8_t CHAR_SPACING = 1;
constexpr uint8_t MAX_TIME_PATTERN_COLUMNS = 32;

Adafruit_NeoPixel matrix(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);

// Map 5x5 character grid indices to physical LEDs in the hex layout.
const uint8_t HEX_LETTER_MAP[ROWS][5] = {
    {0, 1, 2, 3, 4},
    {6, 7, 8, 9, 10},
    {14, 15, 16, 17, 18},
    {22, 23, 24, 25, 26},
    {28, 29, 30, 31, 32}
};

struct Alphabet
{
    char character;
    uint8_t indicies[MAX_CHAR_INDICES];
    uint8_t count;
};

const Alphabet alphabet[] = {
    {'A', {1, 2, 3, 5, 9, 10, 11, 12, 13, 14, 15, 19, 20, 24}, 14},
    {'B', {0, 1, 2, 5, 8, 10, 11, 12, 13, 15, 19, 20, 21, 22, 23}, 15},
    {'C', {1, 2, 3, 5, 9, 10, 15, 19, 21, 22, 23}, 11},
    {'D', {0, 1, 2, 3, 5, 9, 10, 14, 15, 19, 20, 21, 22, 23}, 14},
    {'E', {0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 15, 20, 21, 22, 23, 24}, 16},
    {'F', {0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 15, 20}, 12},
    {'G', {1, 2, 3, 5, 10, 12, 13, 14, 15, 19, 21, 22, 23}, 13},
    {'H', {0, 4, 5, 9, 10, 11, 12, 13, 14, 15, 19, 20, 24}, 13},
    {'I', {1, 2, 3, 7, 12, 17, 21, 22, 23}, 9},
    {'J', {0, 1, 2, 3, 4, 8, 13, 15, 18, 21, 22}, 11},
    {'K', {0, 4, 5, 8, 10, 11, 12, 15, 18, 20, 24}, 11},
    {'L', {1, 6, 11, 16, 21, 22, 23, 24}, 8},
    {'M', {0, 4, 5, 6, 8, 9, 10, 12, 14, 15, 19, 20, 24}, 13},
    {'N', {0, 4, 5, 6, 9, 10, 12, 14, 15, 18, 19, 20, 24}, 13},
    {'O', {1, 2, 3, 5, 9, 10, 14, 15, 19, 21, 22, 23}, 12},
    {'P', {0, 1, 2, 3, 5, 9, 10, 11, 12, 13, 15, 20}, 12},
    {'Q', {1, 2, 5, 8, 10, 13, 15, 18, 21, 22, 23, 24}, 12},
    {'R', {0, 1, 2, 3, 5, 9, 10, 11, 12, 13, 15, 18, 20, 24}, 14},
    {'S', {1, 2, 3, 5, 11, 12, 13, 19, 20, 21, 22, 23}, 12},
    {'T', {0, 1, 2, 3, 4, 7, 12, 17, 22}, 9},
    {'U', {0, 4, 5, 9, 10, 14, 15, 19, 21, 22, 23}, 11},
    {'V', {0, 4, 5, 9, 10, 14, 16, 18, 22}, 9},
    {'W', {0, 4, 5, 9, 10, 12, 14, 15, 17, 19, 21, 23}, 12},
    {'X', {0, 4, 6, 8, 12, 16, 18, 20, 24}, 9},
    {'Y', {0, 4, 6, 8, 12, 17, 22}, 7},
    {'Z', {0, 1, 2, 3, 4, 8, 12, 16, 20, 21, 22, 23, 24}, 13},
    {'0', {1, 2, 3, 5, 6, 9, 10, 12, 14, 15, 18, 19, 21, 22, 23}, 15},
    {'1', {2, 6, 7, 12, 17, 21, 22, 23}, 8},
    {'2', {1, 2, 5, 8, 12, 16, 20, 21, 22, 23}, 10},
    {'3', {1, 2, 5, 8, 12, 15, 18, 21, 22}, 9},
    {'4', {3, 7, 8, 11, 13, 15, 16, 17, 18, 19, 23}, 11},
    {'5', {0, 1, 2, 3, 4, 5, 10, 11, 12, 13, 19, 20, 21, 22, 23}, 15},
    {'6', {1, 2, 3, 5, 10, 11, 12, 13, 15, 19, 21, 22, 23}, 13},
    {'7', {0, 1, 2, 3, 4, 8, 12, 16, 20}, 9},
    {'8', {1, 2, 3, 5, 9, 11, 12, 13, 15, 19, 21, 22, 23}, 13},
    {'9', {1, 2, 3, 5, 9, 11, 12, 13, 14, 19, 21, 22, 23}, 13},
    {':', {7, 17}, 2}
};

const int ALPHABET_SIZE = sizeof(alphabet) / sizeof(alphabet[0]);

constexpr uint8_t BUTTON_NEXT_PIN = 4;
constexpr uint8_t BUTTON_PREV_PIN = 38;

constexpr char ALPHABET_MESSAGE[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
constexpr uint8_t ALPHABET_MESSAGE_LENGTH = sizeof(ALPHABET_MESSAGE) - 1;

enum DisplayMode : uint8_t
{
    MODE_ALPHABET = 0,
    MODE_FACES,
    MODE_TIME,
    MODE_COUNT
};

struct ButtonTracker
{
    uint8_t pin;
    uint8_t lastReading;
    uint8_t stableState;
    unsigned long lastChange;
};

// Simple smile mapped to the hex layout described as:
// --00000--
// -0000000-
// 000000000
// -0000000-
// --00000--
// Only the LED indices listed below are lit for the face.
const uint8_t FACE_SMILE[] = {
    6, 10,          // eyes (row 1)
    16,             // nose (row 2 centre)
    23, 24, 25,     // upper mouth row
    29, 30, 31      // lower mouth row
};

const uint8_t FACE_CUSTOM[] = {0, 4, 5, 7, 9, 11, 29, 30, 31};

struct FaceExpression
{
    const uint8_t* indices;
    uint8_t count;
};

const FaceExpression FACE_EXPRESSIONS[] = {
    {FACE_SMILE, static_cast<uint8_t>(sizeof(FACE_SMILE) / sizeof(FACE_SMILE[0]))},
    {FACE_CUSTOM, static_cast<uint8_t>(sizeof(FACE_CUSTOM) / sizeof(FACE_CUSTOM[0]))}
};

constexpr uint8_t FACE_COUNT = sizeof(FACE_EXPRESSIONS) / sizeof(FACE_EXPRESSIONS[0]);

ButtonTracker buttonNext = {BUTTON_NEXT_PIN, HIGH, HIGH, 0};
ButtonTracker buttonPrev = {BUTTON_PREV_PIN, HIGH, HIGH, 0};

DisplayMode currentMode = MODE_ALPHABET;
uint8_t alphabetIndex = 0;
uint8_t faceIndex = 0;
unsigned long lastStepTimestamp = 0;
bool wifiConnected = false;

uint8_t timePattern[ROWS][MAX_TIME_PATTERN_COLUMNS];
uint8_t timePatternLength = 0;
uint8_t timeScrollOffset = 0;
int8_t timeScrollDirection = 1;
int lastRenderedMinute = -1;

void init_matrix()
{
    matrix.begin();
    matrix.setBrightness(50);
    matrix.show(); // Initialize all pixels to 'off'
}

bool connect_wifi()
{
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Connecting to WiFi");
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start) < WIFI_CONNECT_TIMEOUT_MS)
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    wifiConnected = (WiFi.status() == WL_CONNECTED);
    if (wifiConnected)
    {
        Serial.print("WiFi connected, IP: ");
        Serial.println(WiFi.localIP());
        configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
    }
    else
    {
        Serial.println("WiFi connection failed.");
    }
    return wifiConnected;
}

static uint8_t letter_index_to_led(uint8_t logical_index)
{
    uint8_t row = logical_index / 5;
    uint8_t col = logical_index % 5;
    return HEX_LETTER_MAP[row][col];
}

static const Alphabet* find_alphabet_entry(char c)
{
    for (uint8_t i = 0; i < ALPHABET_SIZE; i++)
    {
        if (alphabet[i].character == c)
        {
            return &alphabet[i];
        }
    }
    return nullptr;
}

void build_pattern_from_text(const char* text, uint8_t pattern[ROWS][MAX_TIME_PATTERN_COLUMNS], uint8_t& length)
{
    for (uint8_t row = 0; row < ROWS; row++)
    {
        memset(pattern[row], 0, MAX_TIME_PATTERN_COLUMNS);
    }
    length = 0;

    for (const char* ptr = text; *ptr != '\0'; ++ptr)
    {
        const Alphabet* entry = find_alphabet_entry(*ptr);
        if (!entry)
        {
            length += CHAR_WIDTH + CHAR_SPACING;
            continue;
        }

        for (uint8_t i = 0; i < entry->count && i < MAX_CHAR_INDICES; i++)
        {
            uint8_t logical_index = entry->indicies[i];
            uint8_t row = logical_index / 5;
            uint8_t col = logical_index % 5;
            uint8_t destCol = length + col;
            if (row < ROWS && destCol < MAX_TIME_PATTERN_COLUMNS)
            {
                pattern[row][destCol] = 1;
            }
        }
        length += CHAR_WIDTH + CHAR_SPACING;
    }
    if (length >= CHAR_SPACING)
    {
        length -= CHAR_SPACING;
    }
}

bool update_time_pattern(bool force)
{
    wifiConnected = (WiFi.status() == WL_CONNECTED);
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo))
    {
        if (!wifiConnected)
        {
            connect_wifi();
        }
        else
        {
            configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
        }
        if (!getLocalTime(&timeinfo))
        {
            Serial.println("Failed to obtain time from NTP");
            return false;
        }
    }

    if (!force && timeinfo.tm_min == lastRenderedMinute)
    {
        return true;
    }

    char buffer[6];
    strftime(buffer, sizeof(buffer), "%H:%M", &timeinfo);
    Serial.print("Time (NTP): ");
    Serial.println(buffer);
    build_pattern_from_text(buffer, timePattern, timePatternLength);
    lastRenderedMinute = timeinfo.tm_min;
    timeScrollOffset = 0;
    timeScrollDirection = 1;
    return true;
}

void render_time_frame(uint32_t color)
{
    matrix.clear();
    for (uint8_t row = 0; row < ROWS; row++)
    {
        for (uint8_t col = 0; col < DISPLAY_WIDTH; col++)
        {
            uint8_t sourceCol = timeScrollOffset + col;
            if (sourceCol < timePatternLength && timePattern[row][sourceCol])
            {
                uint8_t led = HEX_LETTER_MAP[row][col];
                matrix.setPixelColor(led, color);
            }
        }
    }
    matrix.show();
}

void step_time_animation()
{
    const uint32_t color = matrix.Color(255, 200, 0);
    if (!update_time_pattern(false))
    {
        if (timePatternLength > 0)
        {
            render_time_frame(color);
        }
        return;
    }

    if (timePatternLength <= DISPLAY_WIDTH)
    {
        render_time_frame(color);
        return;
    }

    uint8_t maxOffset = timePatternLength - DISPLAY_WIDTH;
    if (timeScrollDirection > 0)
    {
        if (timeScrollOffset < maxOffset)
        {
            timeScrollOffset++;
        }
        else
        {
            timeScrollDirection = -1;
            if (timeScrollOffset > 0)
            {
                timeScrollOffset--;
            }
        }
    }
    else
    {
        if (timeScrollOffset > 0)
        {
            timeScrollOffset--;
        }
        else
        {
            timeScrollDirection = 1;
            if (timeScrollOffset < maxOffset)
            {
                timeScrollOffset++;
            }
        }
    }

    render_time_frame(color);
}

void display_pattern(const uint8_t* indices, uint8_t count, uint32_t color)
{
    matrix.clear();

    for (uint8_t i = 0; i < count; i++)
    {
        uint8_t logical_index = indices[i];
        if (logical_index < ROWS * 5)
        {
            uint8_t led = letter_index_to_led(logical_index);
            matrix.setPixelColor(led, color);
        }
    }

    matrix.show();
}

void display_character(char c, uint32_t color)
{
    const Alphabet* entry = find_alphabet_entry(c);
    if (entry != nullptr)
    {
        display_pattern(entry->indicies, entry->count, color);
    }
    else
    {
        matrix.clear();
        matrix.show();
    }
}

void display_face(uint8_t index, uint32_t color)
{
    const FaceExpression& face = FACE_EXPRESSIONS[index % FACE_COUNT];
    matrix.clear();

    for (uint8_t i = 0; i < face.count; i++)
    {
        uint8_t led = face.indices[i];
        if (led < LED_COUNT)
        {
            matrix.setPixelColor(led, color);
        }
    }

    matrix.show();
}

void showCurrentPattern()
{
    const uint32_t color = matrix.Color(255, 200, 0);
    if (currentMode == MODE_ALPHABET)
    {
        display_character(ALPHABET_MESSAGE[alphabetIndex], color);
    }
    else if (currentMode == MODE_FACES)
    {
        display_face(faceIndex, color);
    }
    else if (currentMode == MODE_TIME)
    {
        if (!update_time_pattern(true) && timePatternLength == 0)
        {
            return;
        }
        render_time_frame(color);
    }
}

void stepCurrentMode()
{
    if (currentMode == MODE_ALPHABET)
    {
        alphabetIndex = static_cast<uint8_t>((alphabetIndex + 1) % ALPHABET_MESSAGE_LENGTH);
        showCurrentPattern();
    }
    else if (currentMode == MODE_FACES)
    {
        faceIndex = static_cast<uint8_t>((faceIndex + 1) % FACE_COUNT);
        showCurrentPattern();
    }
    else if (currentMode == MODE_TIME)
    {
        step_time_animation();
    }
}

bool buttonPressed(ButtonTracker& button)
{
    bool changed = false;
    uint8_t reading = static_cast<uint8_t>(digitalRead(button.pin));
    unsigned long now = millis();

    if (reading != button.lastReading)
    {
        button.lastChange = now;
        button.lastReading = reading;
    }

    if ((now - button.lastChange) > BUTTON_DEBOUNCE_MS)
    {
        if (reading != button.stableState)
        {
            button.stableState = reading;
            if (button.stableState == LOW)
            {
                changed = true;
            }
        }
    }

    return changed;
}

void switchMode(DisplayMode newMode)
{
    if (newMode == currentMode)
    {
        return;
    }

    currentMode = newMode;
    alphabetIndex = 0;
    faceIndex = 0;
    if (currentMode == MODE_TIME)
    {
        timeScrollOffset = 0;
        timeScrollDirection = 1;
        update_time_pattern(true);
    }
    showCurrentPattern();
    lastStepTimestamp = millis();
}

void handleButtons()
{
    if (buttonPressed(buttonNext))
    {
        switchMode(static_cast<DisplayMode>((currentMode + 1) % MODE_COUNT));
    }
    else if (buttonPressed(buttonPrev))
    {
        switchMode(static_cast<DisplayMode>((currentMode + MODE_COUNT - 1) % MODE_COUNT));
    }
}

void setup()
{
    Serial.begin(9600);
    init_matrix();
    connect_wifi();

    pinMode(BUTTON_NEXT_PIN, INPUT_PULLUP);
    pinMode(BUTTON_PREV_PIN, INPUT_PULLUP);

    buttonNext.lastReading = static_cast<uint8_t>(digitalRead(buttonNext.pin));
    buttonNext.stableState = buttonNext.lastReading;
    buttonPrev.lastReading = static_cast<uint8_t>(digitalRead(buttonPrev.pin));
    buttonPrev.stableState = buttonPrev.lastReading;

    showCurrentPattern();
    lastStepTimestamp = millis();
}

void loop()
{
    handleButtons();

    uint32_t interval = (currentMode == MODE_TIME) ? TIME_SCROLL_INTERVAL_MS : DISPLAY_INTERVAL_MS;
    unsigned long now = millis();
    if (now - lastStepTimestamp >= interval)
    {
        lastStepTimestamp = now;
        stepCurrentMode();
    }
}

