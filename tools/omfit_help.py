"""Static OMFIThelp format checks used by both release builders."""
import re


def validate_module_help(data, filename):
    # Mirror OMFIThelp.load/verify: only hyphen-underlined headings delimit
    # sections, and both metadata values must contain a single line.
    text = data.decode('utf-8').replace('\r\n', '\n')
    sections = {}
    for chunk in re.sub(r'\n?(.*)\n-+\n', r'\n>->-> \1 <-<-<', text).split('>->->'):
        parts = [part.strip() for part in chunk.split('<-<-<')]
        if len(parts) > 1:
            sections[parts[0]] = parts[1]
    for name in ('Short Description', 'Keywords'):
        if name not in sections:
            raise ValueError('{}: missing {}'.format(filename, name))
        value = sections[name].strip().strip('\n').strip('.')
        if not value or '\n' in value:
            raise ValueError('{}: {} must be a nonempty single line'.format(filename, name))
    return sections
