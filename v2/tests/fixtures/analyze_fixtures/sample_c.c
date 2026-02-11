#include <stdio.h>
#include <stdlib.h>

struct Point {
    int x;
    int y;
};

int add(int a, int b) {
    return a + b;
}

void print_point(struct Point p) {
    printf("(%d, %d)\n", p.x, p.y);
}

int main(int argc, char *argv[]) {
    struct Point p = {3, 4};
    print_point(p);
    printf("Sum: %d\n", add(1, 2));
    return 0;
}
