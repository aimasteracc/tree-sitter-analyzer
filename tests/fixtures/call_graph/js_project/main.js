// Main module with function calls
function main() {
    const data = loadData();
    const result = process(data);
    save(result);
    helper.greet("world");
    return result;
}

function loadData() {
    return [1, 2, 3];
}

function process(data) {
    return data.map(x => x * 2);
}

function save(result) {
    console.log(result);
}
