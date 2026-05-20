package com.example;

import java.util.List;
import com.example.handler.Handler;
import com.example.model.User;

public class Main {
    public static void main(String[] args) {
        Handler.serve();
        User u = new User();
    }
}
