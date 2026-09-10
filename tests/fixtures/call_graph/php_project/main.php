<?php

function loadData() {
    return 1;
}

function processData($data) {
    return $data * 2;
}

function main() {
    $d = loadData();
    processData($d);
}
