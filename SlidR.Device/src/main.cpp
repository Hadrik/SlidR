#include "Controller.h"

Controller controller;

void setup() {
    controller.begin();
}

void loop() {
    vTaskDelay(portMAX_DELAY);
}