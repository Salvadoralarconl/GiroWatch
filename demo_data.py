"""Entirely fictional Girosol-style data; never added to real training profiles."""


def demo_fixture():
    run_other = ['> LOGIN HQ ...', '> GETTING Girosol ORDER INFORMATION ...',
                 'Sucess!', 'Working on order #:', 'Payer response:',
                 'Status of the order: PENDING', 'Status of the order: PAID',
                 'INFO', '> INITIALIZING TIME ...', '> SENDING ORDER TO INTERBANK ...',
                 '> MAKING PAYMENT CONFIRMATION at Girosol ...',
                 'Success: HQ payment confirmation!', '> PROCESSING ORDER IN GIROSOL WS...',
                 'Success: processed order Code: 0', 'Info: Working on order number',
                 'Info: Order has been sent to payer. Response Code: 10.10.05 Msg:Your remittance will be sent immediately.',
                 'Info: Connection to Interbank API successful.']
    starts = ['> GETTING Girosol ORDER INFORMATION ...', 'Info: Working on order number']
    ends = ['INFO', 'Info: Order has been sent to payer. Response Code: 10.10.05 Msg:Your remittance will be sent immediately.']
    other = [m for m in run_other if m not in starts + ends] + ['BEGIN PROCESS', 'END PROCESS']
    run_profile = {'messages': ['BEGIN PROCESS', 'END PROCESS'] + run_other,
                   'labels': ['Run_Start', 'Run_End'] + ['Other'] * len(run_other)}
    order_profile = {'messages': starts + ends + other,
                     'labels': ['Order_Start'] * 2 + ['Order_End'] * 2 + ['Other'] * len(other),
                     'selected_model': 'nearest_example'}
    lines = []

    def add(minute, *messages):
        lines.extend(f'10/16/2026 09:{minute:02d}:00 AM {message}' for message in messages)

    def order(minute, number, extra=None, paid=False, end=True):
        add(minute, '> GETTING Girosol ORDER INFORMATION ...', 'Sucess!',
            f'Working on order #: 9000000000000000{number}C00', 'Payer response:')
        if extra:
            add(minute, *extra)
        add(minute, 'Status of the order: PAID' if paid else 'Status of the order: PENDING')
        if paid:
            add(minute, '> MAKING PAYMENT CONFIRMATION at Girosol ...',
                'Success: HQ payment confirmation!', '> PROCESSING ORDER IN GIROSOL WS...',
                'Success: processed order Code: 0')
        if end:
            add(minute, 'INFO')

    add(0, 'BEGIN PROCESS', '> INITIALIZING TIME ...')  # Idle start is discarded.
    add(2, 'BEGIN PROCESS', '> LOGIN HQ ...', 'Info: Connection to Interbank API successful. ERROR E400')
    order(2, 1)
    order(2, 2, paid=True)
    add(2, 'Info: Working on order number 90000000000000003C00', '> SENDING ORDER TO INTERBANK ...',
        'Payer response:', 'Info: Order has been sent to payer. Response Code: 10.10.05 Msg:Your remittance will be sent immediately.', 'END PROCESS')
    add(4, 'BEGIN PROCESS', '> LOGIN HQ ...')
    order(4, 1, ['Payer response: ERROR E100 request timed out', 'Payer response: retry succeeded'])
    order(4, 4, ['Payer response: ERROR E200 expected message'])
    add(4, 'END PROCESS')
    add(6, 'BEGIN PROCESS', '> LOGIN HQ ...')
    order(6, 5, ['Payer response: ERROR E300 processing halted'], end=False)
    add(8, 'BEGIN PROCESS', '> LOGIN HQ ...')
    order(8, 6)
    add(8, 'END PROCESS')
    add(10, 'BEGIN PROCESS', '> LOGIN HQ ...')
    order(10, 7, end=False)  # Final run is still pending.
    rules = [
        {'match': 'ERROR E100', 'severity': 'Warning', 'message': 'Demo: request timed out; review the retry.'},
        {'match': 'ERROR E200', 'severity': 'Ignore', 'message': 'Demo: expected response.'},
        {'match': 'ERROR E300', 'severity': 'Critical', 'message': 'Demo: processing halted.'},
        {'match': 'ERROR E400', 'severity': 'Critical', 'message': 'Demo: connection requires review.'},
    ]
    return {'text': '\n'.join(lines), 'run_profile': run_profile,
            'order_profile': order_profile, 'rules': rules}
