#!/sbin/openrc-run

name="myfinance"
description="MyFinance Docker Compose Service"

command="/usr/bin/docker-compose"
command_args="-f /docker/myfinance/docker-compose.yml up -d"
pidfile="/run/${RC_SVCNAME}.pid"

start_pre() {
    checkpath --directory --mode 0755 /docker/myfinance
    if /usr/bin/docker network inspect myfinance_myfin-net >/dev/null 2>&1; then
        ebegin "Removing existing Docker network"
        /usr/bin/docker network rm myfinance_myfin-net
        eend $?
    fi
}

start() {
    ebegin "Starting ${name}"
    /usr/bin/docker-compose -f /docker/myfinance/docker-compose.yml up -d
    eend $?
}

stop() {
    ebegin "Stopping ${name}"
    /usr/bin/docker-compose -f /docker/myfinance/docker-compose.yml down
    eend $?
}

