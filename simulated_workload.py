"""Generate fictional batch work without performing any transactions."""


def build_live_run_events(application, outcome, batch):
    return build_run_events(application, 3, outcome, batch)


def build_run_events(application, count, outcome, batch):
    events = []

    def add(message, level='INFO'):
        events.append((message, level))

    add('================================ BEGIN PROCESS ================================')
    add(f'{application} LOCAL SIMULATION · batch {batch}')
    add('LOGIN HQ OK (SIMULATED)')
    add('LOGIN PAYER OK (SIMULATED)')
    add(f'GETTING PENDING ORDERS: {count} fictional orders')
    add('------------------------------ SENDING ORDERS ------------------------------')
    for index in range(1, count + 1):
        order = f'{batch}{index:03d}'
        add(f'ORDER START: {order}')
        add(f'Working on order #: {order} ({index} of {count})')
        add(f'ORDER: {order} Loading sender and beneficiary (SIMULATED)')
        add(f'ORDER: {order} Validating required fields: OK (SIMULATED)')
        add(f'ORDER: {order} Validating beneficiary account: OK (SIMULATED)')
        add(f'ORDER: {order} Duplicate reference check: clear (SIMULATED)')
        add(f'ORDER: {order} Retrieving payer FX quote (SIMULATED)')
        add(f'ORDER: {order} Amount USD {75 + index * 13:.2f}; quote accepted (FICTIONAL)')
        add(f'ORDER: {order} Preparing payer request (SIMULATED)')
        add(f'ORDER: {order} SENDING ORDER TO PAYER... (SIMULATED; NO NETWORK REQUEST)')
        problem = index == max(1, count // 2)
        failed = problem and outcome == 'Error'
        if problem and outcome == 'Warning':
            add(f'ORDER: {order} SIMULATED WARNING: payer response delayed; retry queued', 'WARNING')
            add(f'ORDER: {order} Retry 1: simulated payer response received')
        if failed:
            add(f'ORDER: {order} SIMULATED ERROR: payer could not process request; retained for review', 'ERROR')
            add(f'ORDER: {order} Recording failed result locally (SIMULATED)')
        else:
            add(f'ORDER: {order} Payer response: accepted (SIMULATED)')
            add(f'ORDER: {order} SIMULATED ORDER SUCCESS')
            add(f'ORDER: {order} Recording confirmation and HQ update (SIMULATED)')
        add(f'ORDER END: {order}')
    failed = int(outcome == 'Error')
    add(f'BATCH SUMMARY: received={count} completed={count-failed} failed={failed} warnings={int(outcome == "Warning")} (SIMULATED)')
    add('LOGOUT PAYER OK (SIMULATED)')
    add('LOGOUT HQ OK (SIMULATED)')
    add('================================ END PROCESS ================================')
    return events
