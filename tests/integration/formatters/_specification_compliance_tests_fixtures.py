"""Fixture source samples for format specification compliance tests."""

ANALYTICS_SERVICE_JAVA = """package com.example.analytics;

import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.ConcurrentHashMap;
import static java.util.Collections.emptyList;

/**
 * Analytics service for processing user data
 * Provides comprehensive analytics functionality
 */
public class AnalyticsService {

    private static final Logger logger = LoggerFactory.getLogger(AnalyticsService.class);
    private final Map<String, Object> cache = new ConcurrentHashMap<>();
    private UserRepository userRepository;
    private boolean enabled = true;

    /**
     * Constructor with repository injection
     * @param userRepository the user repository
     */
    public AnalyticsService(UserRepository userRepository) {
        this.userRepository = userRepository;
        logger.info("AnalyticsService initialized");
    }

    /**
     * Process user analytics data
     * @param userId User ID to process
     * @param metrics List of metrics to calculate
     * @return Analytics result
     * @throws SQLException if database error occurs
     */
    public AnalyticsResult processUserAnalytics(Long userId, List<String> metrics) throws SQLException {
        if (userId == null) {
            throw new IllegalArgumentException("User ID cannot be null");
        }

        User user = userRepository.findById(userId);
        Map<String, Double> results = calculateMetrics(user, metrics);

        return new AnalyticsResult(userId, results);
    }

    /**
     * Calculate metrics for user
     * @param user the user
     * @param metrics list of metrics
     * @return calculated results
     */
    private Map<String, Double> calculateMetrics(User user, List<String> metrics) {
        Map<String, Double> results = new HashMap<>();

        for (String metric : metrics) {
            Double value = calculateSingleMetric(user, metric);
            if (value != null) {
                results.put(metric, value);
            }
        }

        return results;
    }

    /**
     * Calculate single metric
     * @param user the user
     * @param metric metric name
     * @return calculated value
     */
    private Double calculateSingleMetric(User user, String metric) {
        String cacheKey = user.getId() + ":" + metric;

        if (cache.containsKey(cacheKey)) {
            return (Double) cache.get(cacheKey);
        }

        Double result = performCalculation(user, metric);

        if (result != null) {
            cache.put(cacheKey, result);
        }

        return result;
    }

    /**
     * Perform actual calculation
     * @param user the user
     * @param metric metric name
     * @return calculated value
     */
    private Double performCalculation(User user, String metric) {
        switch (metric.toLowerCase()) {
            case "engagement":
                return user.getLoginCount() * 0.1;
            case "retention":
                return Math.max(0.0, 1.0 - (user.getDaysSinceLastLogin() / 30.0));
            default:
                return null;
        }
    }

    /**
     * Clear analytics cache
     */
    public void clearCache() {
        cache.clear();
        logger.info("Analytics cache cleared");
    }

    /**
     * Check if service is enabled
     * @return true if enabled
     */
    public boolean isEnabled() {
        return enabled;
    }

    /**
     * Set service enabled state
     * @param enabled new enabled state
     */
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
        logger.info("AnalyticsService enabled: " + enabled);
    }
}"""
