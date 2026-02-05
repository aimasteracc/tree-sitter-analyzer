package com.example;

public class Service {
    private Helper helper;

    public Service() {
        this.helper = new Helper();
    }

    public void process() {
        validate();
        String data = helper.getData();
        transform(data);
    }

    private void validate() {
        // Validation logic
    }

    private void transform(String input) {
        // Transform logic
    }
}

class Helper {
    public String getData() {
        return "data";
    }
}
