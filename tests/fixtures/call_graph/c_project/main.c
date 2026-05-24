#include <stdio.h>

int loadData(void) {
    return 1;
}

int processData(int data) {
    return data * 2;
}

int main(void) {
    int d = loadData();
    processData(d);
    return 0;
}
