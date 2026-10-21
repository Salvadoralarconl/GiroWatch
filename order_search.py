"""Find whole order occurrences without merging runs or inferring ownership."""
import re

TIMESTAMP = re.compile(r'^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+[AP]M')


def group_error_type(group):
    if group.get('has_alert'):
        return {'Critical': 'Error', 'Warning': 'Warning'}.get(group.get('highest_severity'), 'Error')
    if any(finding.get('severity') == 'Ignore' for finding in group.get('findings', [])):
        return 'Ignore'
    return 'None'


def group_outcome(group, assessed):
    # Search assesses only this occurrence; other groups/run errors cannot affect it.
    if not assessed:
        return 'Not assessed'
    if group.get('has_alert'):
        return 'Error'
    if group.get('status') != 'complete':
        return 'Incomplete'
    return 'Successful'


def search_snapshots(snapshots, query, application='', offset=0):
    query = str(query).strip()
    if len(query) > 120:
        raise ValueError('Enter an order number shorter than 120 characters.')
    try:
        offset = max(0, int(offset))
    except (TypeError, ValueError) as error:
        raise ValueError('Invalid result offset.') from error
    applications = sorted({item['application'] for item in snapshots}, key=str.casefold)
    matches = []
    # Exact alphanumeric token matching: searching ABC12 must not return ABC123.
    pattern = re.compile(r'(?<![A-Za-z0-9])' + re.escape(query) + r'(?![A-Za-z0-9])', re.I) if query else None
    for snapshot in snapshots:
        if not pattern or (application and snapshot['application'].casefold() != application.casefold()):
            continue
        originals = snapshot.get('source_runs', [])
        for position, run in enumerate(snapshot['runs']):
            source = originals[position]['lines'] if position < len(originals) else []
            timestamp = next((m.group() for line in source if (m := TIMESTAMP.match(line))), '')
            for number, group in enumerate(run['orders'], 1):
                if not any(pattern.search(line) for line in group['lines']):
                    continue
                fallback = next((m.group() for line in group['lines'] if (m := TIMESTAMP.match(line))), '')
                matches.append({'application': snapshot['application'], 'source_file': snapshot['filename'],
                                'run_number': run.get('run_number', position + 1), 'group_number': number,
                                'run_time': timestamp or fallback, 'outcome': group_outcome(group, snapshot['errors_assessed']),
                                'severity': group.get('highest_severity', 'None') if group.get('has_alert') else 'None',
                                'error_type': group_error_type(group) if snapshot['errors_assessed'] else 'None',
                                'group_status': group['status'], 'lines': list(group['lines'])})
    # Files are dated; sort newest snapshots first, preserving each occurrence.
    matches.sort(key=lambda item: (item['source_file'], item['run_number'], item['group_number']), reverse=True)
    return {'query': query, 'applications': applications, 'total': len(matches),
            'groups': matches[offset:offset + 50], 'next_offset': offset + 50 if offset + 50 < len(matches) else None}
