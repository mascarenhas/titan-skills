#ifndef SENSOR_H
#define SENSOR_H

typedef struct SensorSample {
  int id;
  double reading;
} SensorSample;

int sensor_scale(int raw);

#endif
