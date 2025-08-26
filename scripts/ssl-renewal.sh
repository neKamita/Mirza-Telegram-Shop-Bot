#!/bin/bash

# SSL Certificate Auto-Renewal Script
# This script handles automatic renewal of SSL certificates using certbot
# and updates nginx configuration with new certificates

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="${PROJECT_ROOT}/ssl"
CERTBOT_DIR="/etc/letsencrypt"
NGINX_SSL_DIR="/app"
LOG_FILE="${PROJECT_ROOT}/logs/ssl-renewal.log"
BACKUP_DIR="${PROJECT_ROOT}/backups/ssl"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    local message="$1"
    log "ERROR" "${RED}${message}${NC}"
    exit 1
}

# Success message
success() {
    local message="$1"
    log "SUCCESS" "${GREEN}${message}${NC}"
}

# Info message
info() {
    local message="$1"
    log "INFO" "${BLUE}${message}${NC}"
}

# Warning message
warning() {
    local message="$1"
    log "WARNING" "${YELLOW}${message}${NC}"
}

# Create necessary directories
create_directories() {
    info "Creating necessary directories..."
    mkdir -p "$SSL_DIR"
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$(dirname "$LOG_FILE")"
}

# Backup current certificates
backup_certificates() {
    local backup_name="ssl_backup_$(date +%Y%m%d_%H%M%S)"
    local backup_path="${BACKUP_DIR}/${backup_name}"

    info "Creating backup of current certificates..."

    if [[ -f "${NGINX_SSL_DIR}/cert.pem" ]]; then
        mkdir -p "$backup_path"
        cp "${NGINX_SSL_DIR}/cert.pem" "$backup_path/" 2>/dev/null || true
        cp "${NGINX_SSL_DIR}/key.pem" "$backup_path/" 2>/dev/null || true
        cp "${NGINX_SSL_DIR}/chain.pem" "$backup_path/" 2>/dev/null || true
        success "Certificates backed up to: $backup_path"
    else
        warning "No existing certificates found to backup"
    fi
}

# Check certificate validity
check_certificate_validity() {
    local cert_file="$1"
    local days_warning="${2:-30}"

    if [[ ! -f "$cert_file" ]]; then
        return 1
    fi

    # Calculate days until expiration
    local expiration_date=$(openssl x509 -in "$cert_file" -noout -enddate 2>/dev/null | cut -d= -f2)
    local expiration_seconds=$(date -d "$expiration_date" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$expiration_date" +%s 2>/dev/null)
    local current_seconds=$(date +%s)
    local days_left=$(( (expiration_seconds - current_seconds) / 86400 ))

    echo "$days_left"
}

# Renew certificates using certbot
renew_certificates() {
    local domain="$1"
    local email="$2"

    info "Attempting to renew certificate for domain: $domain"

    # Check if certbot is available
    if ! command -v certbot &> /dev/null; then
        error_exit "certbot is not installed. Please install certbot first."
    fi

    # Renew certificate
    if certbot renew --webroot -w "$SSL_DIR" --cert-name "$domain" --quiet; then
        success "Certificate renewed successfully"
        return 0
    else
        warning "Certificate renewal failed, attempting fresh certificate..."

        # Try to obtain new certificate
        if certbot certonly --webroot -w "$SSL_DIR" -d "$domain" --email "$email" --agree-tos --no-eff-email --quiet; then
            success "New certificate obtained successfully"
            return 0
        else
            error_exit "Failed to obtain new certificate"
        fi
    fi
}

# Copy certificates to nginx directory
copy_certificates() {
    local domain="$1"
    local certbot_live_dir="${CERTBOT_DIR}/live/${domain}"

    info "Copying certificates to nginx directory..."

    if [[ ! -d "$certbot_live_dir" ]]; then
        error_exit "Certificate directory not found: $certbot_live_dir"
    fi

    # Copy certificates
    cp "${certbot_live_dir}/fullchain.pem" "${NGINX_SSL_DIR}/cert.pem"
    cp "${certbot_live_dir}/privkey.pem" "${NGINX_SSL_DIR}/key.pem"
    cp "${certbot_live_dir}/chain.pem" "${NGINX_SSL_DIR}/chain.pem"

    # Set proper permissions
    chmod 644 "${NGINX_SSL_DIR}/cert.pem"
    chmod 600 "${NGINX_SSL_DIR}/key.pem"
    chmod 644 "${NGINX_SSL_DIR}/chain.pem"

    success "Certificates copied and permissions set"
}

# Test nginx configuration
test_nginx_config() {
    info "Testing nginx configuration..."

    if command -v nginx &> /dev/null; then
        if nginx -t 2>/dev/null; then
            success "Nginx configuration is valid"
            return 0
        else
            warning "Nginx configuration test failed"
            return 1
        fi
    else
        warning "nginx command not found, skipping configuration test"
        return 0
    fi
}

# Reload nginx
reload_nginx() {
    info "Reloading nginx..."

    if command -v nginx &> /dev/null; then
        if nginx -s reload 2>/dev/null; then
            success "Nginx reloaded successfully"
            return 0
        else
            warning "Failed to reload nginx"
            return 1
        fi
    else
        warning "nginx command not found, skipping reload"
        return 0
    fi
}

# Send notification (placeholder for actual notification system)
send_notification() {
    local subject="$1"
    local message="$2"

    info "Sending notification: $subject"

    # Here you can integrate with your notification system
    # Examples: email, Slack, Telegram, etc.

    # For now, just log the notification
    log "NOTIFICATION" "$subject: $message"
}

# Main renewal function
perform_renewal() {
    local domain="$1"
    local email="$2"

    info "Starting SSL certificate renewal process for $domain"

    # Create directories
    create_directories

    # Backup current certificates
    backup_certificates

    # Check current certificate validity
    local days_left=0
    if [[ -f "${NGINX_SSL_DIR}/cert.pem" ]]; then
        days_left=$(check_certificate_validity "${NGINX_SSL_DIR}/cert.pem")
        info "Current certificate expires in $days_left days"
    else
        info "No existing certificate found"
    fi

    # Renew certificates
    if renew_certificates "$domain" "$email"; then
        # Copy certificates to nginx directory
        copy_certificates "$domain"

        # Test nginx configuration
        if test_nginx_config; then
            # Reload nginx
            if reload_nginx; then
                success "SSL certificate renewal completed successfully"

                # Check new certificate validity
                local new_days_left=$(check_certificate_validity "${NGINX_SSL_DIR}/cert.pem")
                info "New certificate expires in $new_days_left days"

                send_notification "SSL Certificate Renewed" "Certificate for $domain has been renewed successfully. Expires in $new_days_left days."
            else
                error_exit "Failed to reload nginx after certificate renewal"
            fi
        else
            error_exit "Nginx configuration test failed after certificate renewal"
        fi
    else
        error_exit "Certificate renewal failed"
    fi
}

# Check if renewal is needed
check_renewal_needed() {
    local domain="$1"
    local days_threshold="${2:-30}"

    if [[ ! -f "${NGINX_SSL_DIR}/cert.pem" ]]; then
        info "No certificate found, renewal needed"
        return 0
    fi

    local days_left=$(check_certificate_validity "${NGINX_SSL_DIR}/cert.pem")

    if [[ $days_left -le $days_threshold ]]; then
        info "Certificate expires in $days_left days, renewal needed"
        return 0
    else
        info "Certificate expires in $days_left days, renewal not needed yet"
        return 1
    fi
}

# Display usage information
usage() {
    cat << EOF
SSL Certificate Auto-Renewal Script

USAGE:
    $0 [OPTIONS] [COMMAND]

COMMANDS:
    renew <domain> <email>    Renew certificate for the specified domain
    check <domain>            Check if renewal is needed for the domain
    backup                    Create backup of current certificates

OPTIONS:
    -h, --help                Show this help message
    -d, --domain DOMAIN       Domain name for certificate
    -e, --email EMAIL         Email address for certificate registration
    -t, --threshold DAYS      Days threshold for renewal check (default: 30)
    -v, --verbose             Enable verbose output

EXAMPLES:
    $0 renew example.com admin@example.com
    $0 check example.com
    $0 backup

CONFIGURATION:
    Set the following environment variables or modify the script:
    - SSL_DIR: Directory for ACME challenges (default: ./ssl)
    - CERTBOT_DIR: Let's Encrypt directory (default: /etc/letsencrypt)
    - NGINX_SSL_DIR: Nginx SSL directory (default: /app)

EOF
}

# Parse command line arguments
parse_args() {
    local command=""
    local domain=""
    local email=""
    local threshold=30

    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -d|--domain)
                domain="$2"
                shift 2
                ;;
            -e|--email)
                email="$2"
                shift 2
                ;;
            -t|--threshold)
                threshold="$2"
                shift 2
                ;;
            -v|--verbose)
                set -x
                shift
                ;;
            renew|check|backup)
                command="$1"
                shift
                break
                ;;
            *)
                error_exit "Unknown option: $1"
                ;;
        esac
    done

    case $command in
        renew)
            if [[ -z "$domain" && $# -gt 0 ]]; then
                domain="$1"
                shift
            fi
            if [[ -z "$email" && $# -gt 0 ]]; then
                email="$1"
                shift
            fi
            if [[ -z "$domain" || -z "$email" ]]; then
                error_exit "Domain and email are required for renewal"
            fi
            perform_renewal "$domain" "$email"
            ;;
        check)
            if [[ -z "$domain" && $# -gt 0 ]]; then
                domain="$1"
                shift
            fi
            if [[ -z "$domain" ]]; then
                error_exit "Domain is required for check"
            fi
            if check_renewal_needed "$domain" "$threshold"; then
                echo "Renewal needed"
                exit 0
            else
                echo "Renewal not needed"
                exit 1
            fi
            ;;
        backup)
            create_directories
            backup_certificates
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

# Main execution
main() {
    # Initialize logging
    touch "$LOG_FILE"

    # Parse arguments
    if [[ $# -eq 0 ]]; then
        usage
        exit 1
    fi

    parse_args "$@"
}

# Run main function with all arguments
main "$@"