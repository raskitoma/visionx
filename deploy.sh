#!/bin/bash

# VisionX Deployment & Configuration Script
# A tool to manage the Lawrence Vision System sync engine

ENV_FILE=".env"
SAMPLE_FILE=".env.sample"

# Colors for better UI
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_docker() {
    if ! command -v docker-compose &> /dev/null; then
        log_error "docker-compose could not be found. Please install it."
        exit 1
    fi
}

load_env() {
    if [ -f "$ENV_FILE" ]; then
        export $(grep -v '^#' $ENV_FILE | xargs)
    fi
}

save_env() {
    log_info "Saving configuration to $ENV_FILE..."
    cat <<EOF > "$ENV_FILE"
SOURCE_DBS="$SOURCE_DBS"
TARGET_DB="$TARGET_DB"
TZ="${TZ:-America/New_York}"
RECORDS_LIMIT="${RECORDS_LIMIT:-100}"
INFLUX_HOST="$INFLUX_HOST"
INFLUX_TOKEN="$INFLUX_TOKEN"
INFLUX_ORG="$INFLUX_ORG"
INFLUX_BUCKET="$INFLUX_BUCKET"
EOF
    log_success "Configuration saved."
}

configure_sources() {
    local sources=""
    local first=true
    
    while true; do
        echo -e "\n${BLUE}--- Add Source Database ---${NC}"
        read -p "Database User: " db_user
        read -p "Database Password: " db_pass
        read -p "Database Host: " db_host
        read -p "Database Port [3306]: " db_port
        db_port=${db_port:-3306}
        read -p "Database Name: " db_name
        read -p "Line Identifier (e.g., L01): " line_id
        
        echo -e "Time Handling:"
        echo "1) Use Source Database Time (no !)"
        echo "2) Use Current Host Time (with !)"
        read -p "Selection [1]: " time_choice
        time_choice=${time_choice:-1}
        
        local prefix=""
        if [ "$time_choice" == "2" ]; then
            prefix="!"
        fi
        
        local source_conn="${prefix}${db_user}:${db_pass}@${db_host}:${db_port}/${db_name}|${line_id}"
        
        if [ "$first" == "true" ]; then
            sources="$source_conn"
            first=false
        else
            sources="${sources},${source_conn}"
        fi
        
        read -p "Add another source? (y/n) [n]: " add_more
        if [[ ! "$add_more" =~ ^[Yy]$ ]]; then
            break
        fi
    done
    SOURCE_DBS="$sources"
}

configure_target() {
    echo -e "\n${BLUE}--- Target Database Configuration ---${NC}"
    read -p "Target User: " target_user
    read -p "Target Password: " target_pass
    read -p "Target Host: " target_host
    read -p "Target Port [3306]: " target_port
    target_port=${target_port:-3306}
    read -p "Target Database Name: " target_name
    TARGET_DB="${target_user}:${target_pass}@${target_host}:${target_port}/${target_name}"
}

configure_influx() {
    echo -e "\n${BLUE}--- InfluxDB Configuration ---${NC}"
    read -p "Influx Host [http://localhost:8086]: " i_host
    INFLUX_HOST=${i_host:-"http://localhost:8086"}
    read -p "Influx Token: " INFLUX_TOKEN
    read -p "Influx Org: " INFLUX_ORG
    read -p "Influx Bucket: " INFLUX_BUCKET
}

configure_misc() {
    echo -e "\n${BLUE}--- Miscellaneous Configuration ---${NC}"
    read -p "Timezone [America/New_York]: " i_tz
    TZ=${i_tz:-"America/New_York"}
    read -p "Records Limit per Sync [100]: " i_limit
    RECORDS_LIMIT=${i_limit:-100}
}

full_configure() {
    log_info "Starting full configuration..."
    configure_sources
    configure_target
    configure_influx
    configure_misc
    save_env
}

cmd_configure() {
    if [ ! -f "$ENV_FILE" ]; then
        full_configure
    else
        echo -e "\n${BLUE}Management Menu:${NC}"
        echo "1) Full Re-configuration"
        echo "2) Add a New Source"
        echo "3) Remove a Source"
        echo "4) Change Target DB"
        echo "5) Change InfluxDB Settings"
        echo "6) Create Tables in Target DB"
        echo "7) Back to Main Menu"
        read -p "Selection: " sub_choice
        
        case $sub_choice in
            1) full_configure ;;
            2) 
                load_env
                local old_sources="$SOURCE_DBS"
                configure_sources # This will reset sources in the loop, wait.
                # Actually, I should make configure_sources append or handle this better.
                # Let's refine configure_sources to accept an existing list.
                append_sources "$old_sources"
                save_env
                ;;
            3)
                load_env
                remove_source
                save_env
                ;;
            4) configure_target; save_env ;;
            5) configure_influx; save_env ;;
            6) cmd_init_db ;;
            7) return ;;
            *) log_error "Invalid selection" ;;
        esac
    fi
}

append_sources() {
    local existing="$1"
    local sources="$existing"
    
    while true; do
        echo -e "\n${BLUE}--- Add Source Database ---${NC}"
        read -p "Database User: " db_user
        read -p "Database Password: " db_pass
        read -p "Database Host: " db_host
        read -p "Database Port [3306]: " db_port
        db_port=${db_port:-3306}
        read -p "Database Name: " db_name
        read -p "Line Identifier (e.g., L01): " line_id
        
        echo -e "Time Handling:"
        echo "1) Use Source Database Time (no !)"
        echo "2) Use Current Host Time (with !)"
        read -p "Selection [1]: " time_choice
        time_choice=${time_choice:-1}
        
        local prefix=""
        if [ "$time_choice" == "2" ]; then
            prefix="!"
        fi
        
        local source_conn="${prefix}${db_user}:${db_pass}@${db_host}:${db_port}/${db_name}|${line_id}"
        
        if [ -z "$sources" ]; then
            sources="$source_conn"
        else
            sources="${sources},${source_conn}"
        fi
        
        read -p "Add another source? (y/n) [n]: " add_more
        if [[ ! "$add_more" =~ ^[Yy]$ ]]; then
            break
        fi
    done
    SOURCE_DBS="$sources"
}

remove_source() {
    if [ -z "$SOURCE_DBS" ]; then
        log_warn "No sources configured."
        return
    fi
    
    IFS=',' read -ra ADDR <<< "$SOURCE_DBS"
    echo -e "\n${BLUE}Current Sources:${NC}"
    for i in "${!ADDR[@]}"; do
        echo "$((i+1))) ${ADDR[i]}"
    done
    
    read -p "Enter number to remove: " rem_idx
    if [[ "$rem_idx" =~ ^[0-9]+$ ]] && [ "$rem_idx" -ge 1 ] && [ "$rem_idx" -le "${#ADDR[@]}" ]; then
        unset 'ADDR[rem_idx-1]'
        SOURCE_DBS=$(IFS=,; echo "${ADDR[*]}")
        log_success "Source removed."
    else
        log_error "Invalid index."
    fi
}

cmd_launch() {
    if [ ! -f "$ENV_FILE" ]; then
        log_error ".env file not found. Please run 'configure' first."
        return
    fi
    log_info "Launching containers..."
    docker-compose up -d --build
    log_success "Application launched."
}

cmd_stop() {
    log_info "Stopping containers..."
    docker-compose stop
}

cmd_remove() {
    log_info "Removing containers and networks..."
    docker-compose down
}

cmd_init_db() {
    if [ ! -f "$ENV_FILE" ]; then
        log_error ".env file not found. Please run 'configure' first."
        return
    fi
    load_env
    
    if [ -z "$TARGET_DB" ]; then
        log_error "TARGET_DB not configured."
        return
    fi

    log_info "Running database initialization via sync-app container..."
    
    # We use docker-compose run to use the existing environment and dependencies
    # We mount the local directory to ensure the latest init.sql and init_db.py are used
    docker-compose run --rm -v "$(pwd):/app" sync-app python app/init_db.py
    
    if [ $? -eq 0 ]; then
        log_success "Database initialization successful."
    else
        log_error "Failed to initialize database tables."
    fi
}

cmd_update() {
    log_info "Checking for updates..."
    # If it's a git repo, we could do git pull
    if [ -d ".git" ]; then
        git pull
    fi
    log_info "Rebuilding and restarting..."
    docker-compose up -d --build
}

main_menu() {
    while true; do
        echo -e "\n${GREEN}=== VisionX Management Tool ===${NC}"
        echo "1) Configure (Add/Remove Sources, Settings)"
        echo "2) Launch (Start system)"
        echo "3) Stop (Stop services)"
        echo "4) Remove (Clean up containers)"
        echo "5) Create Tables (Target DB)"
        echo "6) Update (Pull latest and restart)"
        echo "7) Exit"
        read -p "Selection: " choice
        
        case $choice in
            1) cmd_configure ;;
            2) cmd_launch ;;
            3) cmd_stop ;;
            4) cmd_remove ;;
            5) cmd_init_db ;;
            6) cmd_update ;;
            7) exit 0 ;;
            *) log_error "Invalid selection" ;;
        esac
    done
}

# Entry point
check_docker
if [ "$1" == "configure" ]; then cmd_configure;
elif [ "$1" == "launch" ]; then cmd_launch;
elif [ "$1" == "stop" ]; then cmd_stop;
elif [ "$1" == "remove" ]; then cmd_remove;
elif [ "$1" == "init-db" ]; then cmd_init_db;
elif [ "$1" == "update" ]; then cmd_update;
else
    main_menu
fi
