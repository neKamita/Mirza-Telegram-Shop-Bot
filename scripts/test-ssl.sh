#!/bin/bash

# SSL Configuration Test Script
# This script tests the SSL/TLS configuration for production readiness

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SSL_DIR="${PROJECT_ROOT}/ssl"
LOG_FILE="${PROJECT_ROOT}/logs/ssl-test.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNING=0

# Logging function
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_FILE"
}

# Test result functions
test_pass() {
    local message="$1"
    log "PASS" "${GREEN}${message}${NC}"
    ((TESTS_PASSED++))
}

test_fail() {
    local message="$1"
    log "FAIL" "${RED}${message}${NC}"
    ((TESTS_FAILED++))
}

test_warning() {
    local message="$1"
    log "WARN" "${YELLOW}${message}${NC}"
    ((TESTS_WARNING++))
}

info() {
    local message="$1"
    log "INFO" "${BLUE}${message}${NC}"
}

# Create necessary directories
create_directories() {
    mkdir -p "$(dirname "$LOG_FILE")"
}

# Test certificate files existence
test_certificate_files() {
    info "Testing certificate files existence..."

    local files=("cert.pem" "key.pem" "chain.pem")
    local all_exist=true

    for file in "${files[@]}"; do
        if [[ -f "${SSL_DIR}/${file}" ]]; then
            test_pass "Certificate file ${file} exists"
        else
            test_fail "Certificate file ${file} is missing"
            all_exist=false
        fi
    done

    if [[ "$all_exist" == true ]]; then
        info "All certificate files are present"
    else
        test_fail "Some certificate files are missing"
    fi
}

# Test certificate validity
test_certificate_validity() {
    local cert_file="$1"
    local cert_name="$2"

    info "Testing ${cert_name} validity..."

    if [[ ! -f "$cert_file" ]]; then
        test_fail "${cert_name} file does not exist"
        return 1
    fi

    # Check if certificate is valid
    if openssl x509 -in "$cert_file" -checkend 0 >/dev/null 2>&1; then
        test_pass "${cert_name} is valid"
    else
        test_fail "${cert_name} is expired or invalid"
        return 1
    fi

    # Check expiration date
    local expiration_date=$(openssl x509 -in "$cert_file" -noout -enddate 2>/dev/null | cut -d= -f2)
    local expiration_seconds=$(date -d "$expiration_date" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$expiration_seconds" +%s 2>/dev/null)
    local current_seconds=$(date +%s)
    local days_left=$(( (expiration_seconds - current_seconds) / 86400 ))

    if [[ $days_left -gt 30 ]]; then
        test_pass "${cert_name} expires in $days_left days"
    elif [[ $days_left -gt 7 ]]; then
        test_warning "${cert_name} expires in $days_left days (less than 30 days)"
    else
        test_fail "${cert_name} expires in $days_left days (less than 7 days)"
    fi

    # Check certificate subject
    local subject=$(openssl x509 -in "$cert_file" -noout -subject 2>/dev/null)
    info "${cert_name} subject: $subject"
}

# Test certificate chain
test_certificate_chain() {
    info "Testing certificate chain..."

    if [[ ! -f "${SSL_DIR}/cert.pem" || ! -f "${SSL_DIR}/chain.pem" ]]; then
        test_fail "Certificate or chain file missing for chain test"
        return 1
    fi

    # Create temporary combined certificate for testing
    local temp_cert=$(mktemp)
    cat "${SSL_DIR}/cert.pem" "${SSL_DIR}/chain.pem" > "$temp_cert"

    # Verify certificate chain
    if openssl verify -CAfile "$temp_cert" "${SSL_DIR}/cert.pem" >/dev/null 2>&1; then
        test_pass "Certificate chain is valid"
    else
        test_fail "Certificate chain verification failed"
    fi

    # Clean up
    rm -f "$temp_cert"
}

# Test private key match
test_private_key_match() {
    info "Testing private key and certificate match..."

    if [[ ! -f "${SSL_DIR}/key.pem" || ! -f "${SSL_DIR}/cert.pem" ]]; then
        test_fail "Private key or certificate file missing for match test"
        return 1
    fi

    # Extract public key from certificate
    local cert_modulus=$(openssl x509 -noout -modulus -in "${SSL_DIR}/cert.pem" 2>/dev/null | openssl md5)
    local key_modulus=$(openssl rsa -noout -modulus -in "${SSL_DIR}/key.pem" 2>/dev/null | openssl md5)

    if [[ "$cert_modulus" == "$key_modulus" ]]; then
        test_pass "Private key matches certificate"
    else
        test_fail "Private key does not match certificate"
    fi
}

# Test SSL protocols and ciphers
test_ssl_configuration() {
    local host="${1:-localhost}"
    local port="${2:-443}"

    info "Testing SSL configuration for ${host}:${port}..."

    # Test supported protocols
    info "Testing supported SSL/TLS protocols..."

    local protocols=("ssl2" "ssl3" "tls1" "tls1_1" "tls1_2" "tls1_3")
    local weak_protocols=("ssl2" "ssl3" "tls1" "tls1_1")

    for protocol in "${protocols[@]}"; do
        if echo | openssl s_client -connect "${host}:${port}" -"$protocol" >/dev/null 2>&1; then
            if [[ " ${weak_protocols[*]} " =~ " ${protocol} " ]]; then
                test_fail "Weak protocol $protocol is supported (should be disabled)"
            else
                test_pass "Protocol $protocol is supported"
            fi
        else
            if [[ " ${weak_protocols[*]} " =~ " ${protocol} " ]]; then
                test_pass "Weak protocol $protocol is correctly disabled"
            else
                test_warning "Protocol $protocol is not supported"
            fi
        fi
    done

    # Test cipher suites
    info "Testing cipher suites..."

    if command -v nmap &> /dev/null; then
        local ssl_enum=$(nmap --script ssl-enum-ciphers -p "$port" "$host" 2>/dev/null | grep -E "(TLSv|SSLv)" | head -5)
        if [[ -n "$ssl_enum" ]]; then
            test_pass "SSL cipher enumeration completed"
            info "Detected SSL/TLS versions: $ssl_enum"
        else
            test_warning "Could not enumerate SSL ciphers"
        fi
    else
        test_warning "nmap not available for cipher testing"
    fi
}

# Test nginx configuration
test_nginx_configuration() {
    info "Testing nginx configuration..."

    if command -v nginx &> /dev/null; then
        if nginx -t 2>/dev/null; then
            test_pass "Nginx configuration is valid"
        else
            test_fail "Nginx configuration is invalid"
        fi
    else
        test_warning "nginx command not found, skipping configuration test"
    fi
}

# Test security headers
test_security_headers() {
    local host="${1:-localhost}"
    local port="${2:-443}"

    info "Testing security headers for ${host}:${port}..."

    if command -v curl &> /dev/null; then
        local headers=$(curl -k -s -I "https://${host}:${port}/" 2>/dev/null)

        # Test HSTS header
        if echo "$headers" | grep -q "Strict-Transport-Security"; then
            test_pass "HSTS header is present"
        else
            test_fail "HSTS header is missing"
        fi

        # Test X-Frame-Options header
        if echo "$headers" | grep -q "X-Frame-Options"; then
            test_pass "X-Frame-Options header is present"
        else
            test_fail "X-Frame-Options header is missing"
        fi

        # Test X-Content-Type-Options header
        if echo "$headers" | grep -q "X-Content-Type-Options"; then
            test_pass "X-Content-Type-Options header is present"
        else
            test_fail "X-Content-Type-Options header is missing"
        fi

        # Test Content-Security-Policy header
        if echo "$headers" | grep -q "Content-Security-Policy"; then
            test_pass "Content-Security-Policy header is present"
        else
            test_warning "Content-Security-Policy header is missing"
        fi
    else
        test_warning "curl not available for header testing"
    fi
}

# Test OCSP stapling
test_ocsp_stapling() {
    local host="${1:-localhost}"
    local port="${2:-443}"

    info "Testing OCSP stapling for ${host}:${port}..."

    if command -v openssl &> /dev/null; then
        local ocsp_test=$(echo | openssl s_client -connect "${host}:${port}" -status 2>/dev/null | grep -A 10 "OCSP response")

        if [[ -n "$ocsp_test" ]]; then
            test_pass "OCSP stapling is working"
        else
            test_warning "OCSP stapling test inconclusive"
        fi
    else
        test_warning "openssl not available for OCSP testing"
    fi
}

# Test SSL Labs rating (if available)
test_ssl_labs_rating() {
    local domain="$1"

    info "Testing SSL Labs rating for $domain..."

    if command -v curl &> /dev/null; then
        local ssl_labs_url="https://api.ssllabs.com/api/v3/analyze?host=${domain}"

        # This is a simplified test - in production you might want to use the actual SSL Labs API
        if curl -s "$ssl_labs_url" >/dev/null 2>&1; then
            test_pass "SSL Labs API is accessible for $domain"
            info "Check detailed SSL Labs report at: https://www.ssllabs.com/ssltest/analyze.html?d=${domain}"
        else
            test_warning "Could not access SSL Labs API"
        fi
    else
        test_warning "curl not available for SSL Labs testing"
    fi
}

# Generate test report
generate_report() {
    info "Generating test report..."

    local total_tests=$((TESTS_PASSED + TESTS_FAILED + TESTS_WARNING))
    local success_rate=0

    if [[ $total_tests -gt 0 ]]; then
        success_rate=$(( (TESTS_PASSED * 100) / total_tests ))
    fi

    cat << EOF | tee -a "$LOG_FILE"

========================================
SSL Configuration Test Report
========================================

Test Results:
- Passed: $TESTS_PASSED
- Failed: $TESTS_FAILED
- Warnings: $TESTS_WARNING
- Total: $total_tests
- Success Rate: ${success_rate}%

EOF

    if [[ $TESTS_FAILED -eq 0 ]]; then
        if [[ $TESTS_WARNING -eq 0 ]]; then
            log "RESULT" "${GREEN}All tests passed! SSL configuration is production-ready.${NC}"
        else
            log "RESULT" "${YELLOW}All critical tests passed, but some warnings need attention.${NC}"
        fi
    else
        log "RESULT" "${RED}Some critical tests failed. Please review and fix the issues.${NC}"
    fi

    cat << EOF | tee -a "$LOG_FILE"

Recommendations:
1. Fix all FAILED tests before deploying to production
2. Review WARNING tests and address if possible
3. Regularly run this test script to monitor SSL health
4. Set up automated monitoring and alerting for SSL certificate expiration

========================================

EOF
}

# Main test function
run_all_tests() {
    local domain="${1:-}"
    local host="${2:-localhost}"
    local port="${3:-443}"

    info "Starting SSL configuration tests..."
    info "Domain: $domain"
    info "Host: $host"
    info "Port: $port"

    # Basic certificate tests
    test_certificate_files
    if [[ -f "${SSL_DIR}/cert.pem" ]]; then
        test_certificate_validity "${SSL_DIR}/cert.pem" "Certificate"
    fi
    if [[ -f "${SSL_DIR}/chain.pem" ]]; then
        test_certificate_validity "${SSL_DIR}/chain.pem" "Certificate Chain"
    fi
    test_certificate_chain
    test_private_key_match

    # SSL configuration tests
    test_ssl_configuration "$host" "$port"
    test_nginx_configuration
    test_security_headers "$host" "$port"
    test_ocsp_stapling "$host" "$port"

    # External tests
    if [[ -n "$domain" ]]; then
        test_ssl_labs_rating "$domain"
    fi

    # Generate report
    generate_report
}

# Usage information
usage() {
    cat << EOF
SSL Configuration Test Script

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -d, --domain DOMAIN     Domain name to test
    -h, --host HOST         Host to test (default: localhost)
    -p, --port PORT         Port to test (default: 443)
    --help                  Show this help message

EXAMPLES:
    $0 -d example.com
    $0 -d example.com -h 192.168.1.100 -p 8443
    $0 --domain example.com --host production.example.com

DESCRIPTION:
    This script performs comprehensive SSL/TLS configuration testing including:
    - Certificate file existence and validity
    - Certificate chain verification
    - Private key matching
    - SSL/TLS protocol support
    - Security headers presence
    - OCSP stapling functionality
    - Nginx configuration validity

EOF
}

# Parse command line arguments
parse_args() {
    local domain=""
    local host="localhost"
    local port="443"

    while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--domain)
                domain="$2"
                shift 2
                ;;
            -h|--host)
                host="$2"
                shift 2
                ;;
            -p|--port)
                port="$2"
                shift 2
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1" >&2
                usage
                exit 1
                ;;
        esac
    done

    run_all_tests "$domain" "$host" "$port"
}

# Main execution
main() {
    create_directories

    if [[ $# -eq 0 ]]; then
        # Run basic tests without domain
        run_all_tests
    else
        parse_args "$@"
    fi
}

# Run main function with all arguments
main "$@"