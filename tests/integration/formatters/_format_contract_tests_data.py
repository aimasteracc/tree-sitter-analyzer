"""Fixture data for format contract integration tests."""

import tempfile
from pathlib import Path

FORMAT_TYPES = ("full", "compact", "csv")
CONTRACT_CLASS_NAME = "ContractTestService"

CONTRACT_TEST_SERVICE_JAVA_CONTENT = """package com.example.contracts;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

/**
 * Contract testing service
 * Demonstrates comprehensive class structure for format contract validation
 */
public class ContractTestService {

    // Static fields
    private static final String SERVICE_NAME = "ContractTestService";
    private static final int MAX_RETRIES = 3;

    // Instance fields
    private final Map<String, Object> configuration;
    private List<String> activeConnections;
    private boolean isInitialized = false;

    /**
     * Default constructor
     */
    public ContractTestService() {
        this.configuration = new HashMap<>();
        this.activeConnections = new ArrayList<>();
    }

    /**
     * Constructor with configuration
     * @param config initial configuration
     */
    public ContractTestService(Map<String, Object> config) {
        this.configuration = new HashMap<>(config);
        this.activeConnections = new ArrayList<>();
        this.isInitialized = true;
    }

    /**
     * Initialize the service
     * @param timeout timeout in milliseconds
     * @return initialization result
     */
    public CompletableFuture<Boolean> initialize(long timeout) {
        return CompletableFuture.supplyAsync(() -> {
            // Initialization logic
            this.isInitialized = true;
            return true;
        });
    }

    /**
     * Process data with multiple parameters
     * @param data input data list
     * @param options processing options
     * @param callback completion callback
     * @return processing result
     */
    public Optional<String> processData(
        List<String> data,
        Map<String, Object> options,
        Runnable callback
    ) {
        if (!isInitialized) {
            return Optional.empty();
        }

        // Processing logic
        callback.run();
        return Optional.of("processed");
    }

    /**
     * Get service configuration
     * @return configuration map
     */
    public Map<String, Object> getConfiguration() {
        return new HashMap<>(configuration);
    }

    /**
     * Update configuration
     * @param key configuration key
     * @param value configuration value
     */
    public void updateConfiguration(String key, Object value) {
        configuration.put(key, value);
    }

    /**
     * Check if service is initialized
     * @return true if initialized
     */
    public boolean isInitialized() {
        return isInitialized;
    }

    /**
     * Get active connections count
     * @return number of active connections
     */
    public int getActiveConnectionsCount() {
        return activeConnections.size();
    }

    /**
     * Add connection
     * @param connectionId connection identifier
     */
    public void addConnection(String connectionId) {
        if (!activeConnections.contains(connectionId)) {
            activeConnections.add(connectionId);
        }
    }

    /**
     * Remove connection
     * @param connectionId connection identifier
     * @return true if connection was removed
     */
    public boolean removeConnection(String connectionId) {
        return activeConnections.remove(connectionId);
    }

    /**
     * Shutdown the service
     */
    public void shutdown() {
        activeConnections.clear();
        configuration.clear();
        isInitialized = false;
    }
}"""


def create_comprehensive_contract_fixture() -> tuple[str, Path, str]:
    """Create the Java source file used by format contract tests."""
    temp_dir = tempfile.mkdtemp()
    test_file = Path(temp_dir) / f"{CONTRACT_CLASS_NAME}.java"
    test_file.write_text(CONTRACT_TEST_SERVICE_JAVA_CONTENT, encoding="utf-8")
    return temp_dir, test_file, CONTRACT_CLASS_NAME


def cleanup_comprehensive_contract_fixture(temp_dir: str, test_file: Path) -> None:
    """Remove the Java source fixture and temporary directory."""
    test_file.unlink()
    Path(temp_dir).rmdir()
