#!/sbin/openrc-run

name="myfinance"
description="MyFinance Docker Compose Service"

command="/docker/myfinance/mfcompose"
command_args="up -d"
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
    /docker/myfinance/mfcompose up -d
    eend $?
}

stop() {
    ebegin "Stopping ${name}"
    /docker/myfinance/mfcompose down
    eend $?
}

