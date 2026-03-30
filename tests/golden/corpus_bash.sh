#!/usr/bin/env bash
#
# Bash Golden Corpus - Grammar Coverage MECE Test
#
# This file contains all key node types from tree-sitter-bash grammar
# to verify complete coverage of Bash language features.
#
# Coverage includes:
# - Function definitions
# - Variable assignments (declaration_command)
# - Control flow (if, while, for, case)
# - Commands (simple_command, command)
# - Pipelines
# - Redirections
# - Command substitution
# - Process substitution
# - Here-documents
# - Arrays
# - Arithmetic expansion

# ============================================================================
# Variable Assignments
# ============================================================================

# Simple variable assignment
SIMPLE_VAR="hello"
NUMBER=42
EMPTY_VAR=""

# Variable with command substitution
CURRENT_DATE=$(date +%Y-%m-%d)
USER_NAME=`whoami`

# Variable with arithmetic
COUNT=$((10 + 20))
RESULT=$((5 * 3))

# Array assignment
SIMPLE_ARRAY=(one two three)
INDEXED_ARRAY[0]="first"
INDEXED_ARRAY[1]="second"

# Associative array (requires declare)
declare -A ASSOC_ARRAY
ASSOC_ARRAY[key1]="value1"
ASSOC_ARRAY[key2]="value2"

# Export variable
export PATH="/usr/local/bin:$PATH"
export EDITOR="vim"

# Read-only variable
readonly CONSTANT="immutable"

# Local variable (inside function)
function local_var_example() {
    local LOCAL_VAR="local scope"
    echo "$LOCAL_VAR"
}

# ============================================================================
# Declaration Commands
# ============================================================================

# Declare integer
declare -i INTEGER_VAR=100

# Declare array
declare -a ARRAY_VAR=(a b c)

# Declare associative array
declare -A MAP_VAR

# Declare read-only
declare -r READONLY_VAR="constant"

# Declare exported variable
declare -x EXPORTED_VAR="exported"

# Multiple declarations
declare VAR1="first" VAR2="second"

# ============================================================================
# Function Definitions
# ============================================================================

# Simple function (function keyword)
function simple_function() {
    echo "Simple function"
}

# Function without 'function' keyword
another_function() {
    echo "Another function"
}

# Function with parameters
function greet() {
    local name="$1"
    local greeting="${2:-Hello}"
    echo "$greeting, $name!"
}

# Function with return value
function add_numbers() {
    local a=$1
    local b=$2
    local result=$((a + b))
    echo "$result"
}

# Function with return status
function check_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        return 0
    else
        return 1
    fi
}

# Nested function definition
function outer_function() {
    function inner_function() {
        echo "Inner function"
    }
    inner_function
}

# Function with command substitution
function get_timestamp() {
    echo "$(date +%s)"
}

# Function with pipeline
function count_lines() {
    cat "$1" | wc -l
}

# Function with here-document
function print_message() {
    cat <<EOF
This is a multi-line
message from a function
EOF
}

# ============================================================================
# Control Flow - If Statements
# ============================================================================

# Simple if statement
if [[ $NUMBER -gt 10 ]]; then
    echo "Greater than 10"
fi

# If-else statement
if [[ -f "/etc/passwd" ]]; then
    echo "File exists"
else
    echo "File does not exist"
fi

# If-elif-else statement
if [[ $COUNT -lt 10 ]]; then
    echo "Less than 10"
elif [[ $COUNT -eq 10 ]]; then
    echo "Equal to 10"
else
    echo "Greater than 10"
fi

# Nested if statement
if [[ $NUMBER -gt 0 ]]; then
    if [[ $NUMBER -lt 100 ]]; then
        echo "Between 0 and 100"
    fi
fi

# If with command test
if grep -q "pattern" /tmp/file.txt; then
    echo "Pattern found"
fi

# If with multiple conditions
if [[ $NUMBER -gt 0 && $NUMBER -lt 100 ]]; then
    echo "Valid range"
fi

# ============================================================================
# Control Flow - While Statements
# ============================================================================

# Simple while loop
counter=0
while [[ $counter -lt 5 ]]; do
    echo "Counter: $counter"
    ((counter++))
done

# While with read
while read -r line; do
    echo "Line: $line"
done < /tmp/input.txt

# While with command
while ps aux | grep -q "[s]ome_process"; do
    sleep 1
done

# Infinite while loop
# while true; do
#     echo "Running..."
#     break
# done

# ============================================================================
# Control Flow - For Statements
# ============================================================================

# For loop with list
for item in one two three; do
    echo "Item: $item"
done

# For loop with range
for i in {1..5}; do
    echo "Number: $i"
done

# For loop with command substitution
for file in $(ls /tmp); do
    echo "File: $file"
done

# For loop with array
for element in "${SIMPLE_ARRAY[@]}"; do
    echo "Element: $element"
done

# C-style for loop
for ((i = 0; i < 10; i++)); do
    echo "Index: $i"
done

# For loop with glob pattern
for file in /tmp/*.txt; do
    if [[ -f "$file" ]]; then
        echo "Text file: $file"
    fi
done

# ============================================================================
# Control Flow - Case Statements
# ============================================================================

# Simple case statement
case "$SIMPLE_VAR" in
    "hello")
        echo "Greeting"
        ;;
    "goodbye")
        echo "Farewell"
        ;;
    *)
        echo "Unknown"
        ;;
esac

# Case with patterns
case "$NUMBER" in
    [0-9])
        echo "Single digit"
        ;;
    [0-9][0-9])
        echo "Two digits"
        ;;
    *)
        echo "Other"
        ;;
esac

# Case with multiple patterns
FILE_EXT="${1##*.}"
case "$FILE_EXT" in
    txt|log)
        echo "Text file"
        ;;
    jpg|png|gif)
        echo "Image file"
        ;;
    sh|bash)
        echo "Shell script"
        ;;
    *)
        echo "Unknown type"
        ;;
esac

# ============================================================================
# Simple Commands
# ============================================================================

# Basic commands
echo "Hello, World!"
printf "Formatted output: %s\n" "test"
ls -la
pwd
cd /tmp
mkdir -p /tmp/test/nested
touch /tmp/test/file.txt
rm -f /tmp/test/file.txt

# Commands with arguments
grep "pattern" /tmp/file.txt
sed 's/old/new/g' /tmp/file.txt
awk '{print $1}' /tmp/file.txt
sort /tmp/file.txt
uniq /tmp/file.txt
cut -d: -f1 /etc/passwd

# ============================================================================
# Pipelines
# ============================================================================

# Simple pipeline
cat /tmp/file.txt | grep "pattern"

# Multiple stage pipeline
ps aux | grep "process" | awk '{print $2}'

# Pipeline with redirection
cat /tmp/input.txt | sort | uniq > /tmp/output.txt

# Pipeline with error handling
cat /tmp/file.txt | grep "pattern" | head -n 10

# Complex pipeline
find /tmp -name "*.txt" | xargs grep "search" | sort | uniq -c

# Pipeline with tee
echo "Log message" | tee -a /tmp/logfile.txt

# ============================================================================
# Redirections
# ============================================================================

# Output redirection
echo "Output" > /tmp/output.txt
echo "Append" >> /tmp/output.txt

# Input redirection
wc -l < /tmp/input.txt

# Error redirection
command 2> /tmp/error.log

# Redirect stdout and stderr
command > /tmp/output.txt 2>&1

# Redirect stderr to stdout
command 2>&1 | grep "error"

# Redirect to null device
command > /dev/null 2>&1

# File descriptor redirection
exec 3< /tmp/input.txt
exec 4> /tmp/output.txt

# Here-string
grep "pattern" <<< "text to search"

# ============================================================================
# Here-documents
# ============================================================================

# Simple here-document
cat <<EOF
This is a multi-line
document embedded in
the shell script
EOF

# Here-document with variable expansion
cat <<EOF
Current user: $USER
Current directory: $PWD
EOF

# Here-document without variable expansion
cat <<'EOF'
Literal $USER
Literal $PWD
EOF

# Indented here-document
cat <<-EOF
	Indented line 1
	Indented line 2
EOF

# Here-document to file
cat <<EOF > /tmp/heredoc.txt
Content for file
Multiple lines
EOF

# ============================================================================
# Command Substitution
# ============================================================================

# Modern command substitution $()
FILES=$(ls /tmp)
DATE_STRING=$(date +%Y-%m-%d)
LINE_COUNT=$(wc -l < /tmp/file.txt)

# Nested command substitution
NESTED=$(echo "Result: $(date +%s)")

# Backtick command substitution (old style)
OLD_STYLE=`date`
ANOTHER_OLD=`ls -l /tmp`

# Command substitution in string
MESSAGE="Current time is $(date)"

# ============================================================================
# Process Substitution
# ============================================================================

# Compare output of two commands
diff <(sort file1.txt) <(sort file2.txt)

# Use process substitution as input
while read -r line; do
    echo "Line: $line"
done < <(ls -l)

# Multiple process substitutions
paste <(cut -f1 file1.txt) <(cut -f2 file2.txt)

# ============================================================================
# Arithmetic Expansion
# ============================================================================

# Simple arithmetic
result=$((5 + 3))
result=$((10 - 2))
result=$((4 * 7))
result=$((20 / 4))
result=$((17 % 5))

# Arithmetic with variables
a=10
b=20
sum=$((a + b))
product=$((a * b))

# Increment/decrement
((counter++))
((counter--))
((counter += 5))
((counter -= 2))

# Comparison in arithmetic
if ((NUMBER > 10)); then
    echo "Greater than 10"
fi

# Arithmetic in condition
while ((counter < 100)); do
    ((counter++))
done

# ============================================================================
# Test Commands
# ============================================================================

# Test with [ ] (old style)
if [ -f "/tmp/file.txt" ]; then
    echo "File exists"
fi

# Test with [[ ]] (modern, recommended)
if [[ -d "/tmp" ]]; then
    echo "Directory exists"
fi

# String comparison
if [[ "$SIMPLE_VAR" == "hello" ]]; then
    echo "Match"
fi

# Numeric comparison
if [[ $NUMBER -gt 10 ]]; then
    echo "Greater"
fi

# File tests
[[ -r "/tmp/file.txt" ]] && echo "Readable"
[[ -w "/tmp/file.txt" ]] && echo "Writable"
[[ -x "/tmp/file.txt" ]] && echo "Executable"

# ============================================================================
# Subshells and Command Groups
# ============================================================================

# Subshell
(cd /tmp && ls -la)

# Command group
{ echo "First"; echo "Second"; }

# Subshell with pipeline
(cat file1.txt; cat file2.txt) | grep "pattern"

# ============================================================================
# Background Jobs
# ============================================================================

# Run command in background
# sleep 10 &

# Get background job PID
# BACKGROUND_PID=$!

# Wait for background job
# wait $BACKGROUND_PID

# ============================================================================
# Special Variables
# ============================================================================

# Script arguments
echo "Script name: $0"
echo "First argument: $1"
echo "All arguments: $@"
echo "Argument count: $#"

# Exit status
command
EXIT_STATUS=$?

# Process ID
echo "Current PID: $$"

# Last background PID
# echo "Last background PID: $!"

# ============================================================================
# String Operations
# ============================================================================

# String length
echo "${#SIMPLE_VAR}"

# Substring extraction
echo "${SIMPLE_VAR:0:5}"

# String replacement
echo "${SIMPLE_VAR/hello/hi}"

# Default values
echo "${UNDEFINED_VAR:-default}"
echo "${UNDEFINED_VAR:=default}"

# ============================================================================
# End of Golden Corpus
# ============================================================================
