// Package sample demonstrates Go language features for tree-sitter-analyzer.
// This file contains examples of various Go constructs including:
// - Package declaration
// - Imports
// - Functions and methods
// - Structs and interfaces
// - Type aliases
// - Constants and variables
// - Goroutines and channels
package sample

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

// ErrNotFound is returned when a resource is not found.
var ErrNotFound = errors.New("resource not found")

// DefaultTimeout is the default timeout for operations.
const DefaultTimeout = 30 * time.Second

// MaxRetries defines the maximum number of retry attempts.
const (
	MaxRetries    = 3
	RetryInterval = time.Second
)

// Status represents the status of an operation.
type Status int

// Status constants
const (
	StatusPending Status = iota
	StatusRunning
	StatusCompleted
	StatusFailed
)

// Config holds configuration options.
type Config struct {
	Host     string
	Port     int
	Timeout  time.Duration
	Debug    bool
	metadata map[string]string
}

// Reader is an interface for reading data.
type Reader interface {
	// Read reads data into the provided buffer.
	Read(p []byte) (n int, err error)
}

// Writer is an interface for writing data.
type Writer interface {
	// Write writes data from the provided buffer.
	Write(p []byte) (n int, err error)
}

// ReadWriter combines Reader and Writer interfaces.
type ReadWriter interface {
	Reader
	Writer
}

// Service represents a background service.
type Service struct {
	name    string
	config  *Config
	running bool
	mu      sync.RWMutex
	done    chan struct{}
}

// NewService creates a new Service instance.
func NewService(name string, config *Config) *Service {
	return &Service{
		name:   name,
		config: config,
		done:   make(chan struct{}),
	}
}

// Name returns the service name.
func (s *Service) Name() string {
	return s.name
}

// IsRunning checks if the service is currently running.
func (s *Service) IsRunning() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.running
}

// Start starts the service.
func (s *Service) Start(ctx context.Context) error {
	s.mu.Lock()
	if s.running {
		s.mu.Unlock()
		return errors.New("service already running")
	}
	s.running = true
	s.mu.Unlock()

	// Start background goroutine
	go s.run(ctx)

	return nil
}

// run is the main service loop.
func (s *Service) run(ctx context.Context) {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			s.stop()
			return
		case <-s.done:
			return
		case t := <-ticker.C:
			s.tick(t)
		}
	}
}

// tick handles periodic tasks.
func (s *Service) tick(t time.Time) {
	if s.config.Debug {
		fmt.Printf("[%s] tick at %v\n", s.name, t)
	}
}

// Stop stops the service gracefully.
func (s *Service) Stop() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.running {
		return errors.New("service not running")
	}

	close(s.done)
	s.running = false
	return nil
}

// stop is an internal method to mark service as stopped.
func (s *Service) stop() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.running = false
}

// ProcessData processes data using channels and goroutines.
func ProcessData(ctx context.Context, input <-chan []byte) (<-chan []byte, <-chan error) {
	output := make(chan []byte)
	errs := make(chan error, 1)

	go func() {
		defer close(output)
		defer close(errs)

		for {
			select {
			case <-ctx.Done():
				errs <- ctx.Err()
				return
			case data, ok := <-input:
				if !ok {
					return
				}
				// Process data
				processed := process(data)
				select {
				case output <- processed:
				case <-ctx.Done():
					errs <- ctx.Err()
					return
				}
			}
		}
	}()

	return output, errs
}

// process is a helper function for data processing.
func process(data []byte) []byte {
	// Simple transformation
	result := make([]byte, len(data))
	for i, b := range data {
		result[i] = b ^ 0xFF
	}
	return result
}

// WorkerPool manages a pool of workers.
type WorkerPool struct {
	workers int
	jobs    chan func()
	wg      sync.WaitGroup
}

// NewWorkerPool creates a new worker pool.
func NewWorkerPool(workers int) *WorkerPool {
	return &WorkerPool{
		workers: workers,
		jobs:    make(chan func(), workers*2),
	}
}

// Start starts the worker pool.
func (p *WorkerPool) Start() {
	for i := 0; i < p.workers; i++ {
		p.wg.Add(1)
		go p.worker()
	}
}

// worker is the goroutine that processes jobs.
func (p *WorkerPool) worker() {
	defer p.wg.Done()
	for job := range p.jobs {
		job()
	}
}

// Submit submits a job to the pool.
func (p *WorkerPool) Submit(job func()) {
	p.jobs <- job
}

// Shutdown shuts down the worker pool.
func (p *WorkerPool) Shutdown() {
	close(p.jobs)
	p.wg.Wait()
}

// StringSlice is a type alias for []string.
type StringSlice = []string

// Handler is a function type for handling requests.
type Handler func(ctx context.Context, req interface{}) (interface{}, error)

// Middleware wraps a Handler with additional functionality.
type Middleware func(Handler) Handler

// Chain chains multiple middlewares together.
func Chain(middlewares ...Middleware) Middleware {
	return func(next Handler) Handler {
		for i := len(middlewares) - 1; i >= 0; i-- {
			next = middlewares[i](next)
		}
		return next
	}
}

// WithTimeout adds timeout to a handler.
func WithTimeout(timeout time.Duration) Middleware {
	return func(next Handler) Handler {
		return func(ctx context.Context, req interface{}) (interface{}, error) {
			ctx, cancel := context.WithTimeout(ctx, timeout)
			defer cancel()
			return next(ctx, req)
		}
	}
}

// WithRetry adds retry logic to a handler.
func WithRetry(maxRetries int) Middleware {
	return func(next Handler) Handler {
		return func(ctx context.Context, req interface{}) (interface{}, error) {
			var lastErr error
			for i := 0; i < maxRetries; i++ {
				resp, err := next(ctx, req)
				if err == nil {
					return resp, nil
				}
				lastErr = err
				time.Sleep(RetryInterval)
			}
			return nil, lastErr
		}
	}
}
