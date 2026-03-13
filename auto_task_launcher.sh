#!/bin/bash
# Auto-Task Launcher: Monitors blocked tasks and launches when blockers complete

set -e

LOG_FILE="$HOME/.claude/logs/auto_launcher.log"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to check if task is complete
is_task_complete() {
    local task_id=$1
    status=$(task get "$task_id" | grep "status" | awk '{print $NF}')
    [ "$status" = "completed" ]
}

# Function to launch task with agent
launch_task() {
    local task_id=$1
    local agent_name=$2

    log "🚀 Launching Task #$task_id with $agent_name..."

    # Mark task as in_progress
    task update "$task_id" status in_progress

    # Launch agent in background
    case $task_id in
        6)
            # Task #6: Level 1 Optimization
            agent start --task 6 --name "$agent_name" --type python-backend-engineer &
            ;;
        7)
            # Task #7: Level 3 Robustness
            agent start --task 7 --name "$agent_name" --type python-backend-engineer &
            ;;
        8)
            # Task #8: Skill Management
            agent start --task 8 --name "$agent_name" --type python-backend-engineer &
            ;;
        9)
            # Task #9: Testing & Quality
            agent start --task 9 --name "$agent_name" --type qa-testing-agent &
            ;;
        10)
            # Task #10: Performance Optimization
            agent start --task 10 --name "$agent_name" --type python-backend-engineer &
            ;;
        11)
            # Task #11: User Experience
            agent start --task 11 --name "$agent_name" --type python-backend-engineer &
            ;;
    esac

    log "✅ Task #$task_id launched successfully"
}

# Monitor Task #2 completion
monitor_task_2() {
    log "⏳ Waiting for Task #2 to complete..."
    while ! is_task_complete 2; do
        sleep 30
    done
    log "✅ Task #2 completed! Launching Task #6..."
    launch_task 6 "Agent-E"
}

# Monitor Task #4 completion
monitor_task_4() {
    log "⏳ Waiting for Task #4 to complete..."
    while ! is_task_complete 4; do
        sleep 30
    done
    log "✅ Task #4 completed! Launching Task #7 and #8..."
    launch_task 7 "Agent-F"
    launch_task 8 "Agent-G"
}

# Monitor Task #5 completion
monitor_task_5() {
    log "⏳ Waiting for Task #5 to complete..."
    while ! is_task_complete 5; do
        sleep 30
    done
    log "✅ Task #5 completed! Launching Task #9..."
    launch_task 9 "Agent-H"
}

# Monitor Task #7 completion
monitor_task_7() {
    log "⏳ Waiting for Task #7 to complete..."
    while ! is_task_complete 7; do
        sleep 30
    done
    log "✅ Task #7 completed! Launching Task #10..."
    launch_task 10 "Agent-I"
}

# Monitor Task #8 completion
monitor_task_8() {
    log "⏳ Waiting for Task #8 to complete..."
    while ! is_task_complete 8; do
        sleep 30
    done
    log "✅ Task #8 completed! Launching Task #11..."
    launch_task 11 "Agent-J"
}

# Main execution
main() {
    log "═════════════════════════════════════════"
    log "🚀 Auto-Task Launcher Started"
    log "═════════════════════════════════════════"
    log ""
    log "Dependencies:"
    log "  Task #2 → Task #6"
    log "  Task #4 → Task #7 + Task #8"
    log "  Task #5 → Task #9"
    log "  Task #7 → Task #10"
    log "  Task #8 → Task #11"
    log ""

    # Start all monitors in parallel
    monitor_task_2 &
    PID_2=$!

    monitor_task_4 &
    PID_4=$!

    monitor_task_5 &
    PID_5=$!

    monitor_task_7 &
    PID_7=$!

    monitor_task_8 &
    PID_8=$!

    log "All monitors started in background"
    log "  Monitor 2: PID $PID_2"
    log "  Monitor 4: PID $PID_4"
    log "  Monitor 5: PID $PID_5"
    log "  Monitor 7: PID $PID_7"
    log "  Monitor 8: PID $PID_8"
    log ""

    # Wait for all monitors
    wait $PID_2 $PID_4 $PID_5 $PID_7 $PID_8

    log "═════════════════════════════════════════"
    log "✅ All Tasks Launched Successfully!"
    log "═════════════════════════════════════════"
}

# Error handling
trap 'log "❌ Auto-launcher failed"; exit 1' ERR

# Run main
main "$@"
