#!/sbin/openrc-run

name="myfinance"
description="MyFinance Docker Compose Service"

command="/usr/bin/docker-compose"
command_args="-f /docker/myfinance/docker-compose.yml up -d"
pidfile="/run/${RC_SVCNAME}.pid"

depend() {
    need docker
    after networking
}

start_pre() {
    checkpath --directory --mode 0755 /docker/myfinance
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

