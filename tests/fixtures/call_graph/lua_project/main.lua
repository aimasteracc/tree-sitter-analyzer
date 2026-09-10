function loadData()
    return 1
end

function processData(data)
    return data * 2
end

function main()
    local d = loadData()
    processData(d)
end
