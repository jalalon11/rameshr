import io
import os

p = os.path.join(os.path.dirname(__file__), '..', 'load_data', 'mail_automations.json')
# normalize path
p = os.path.abspath(p)

with io.open(p, 'r', encoding='utf-8') as f:
    s = f.read()

# Replace both plain and HTML-escaped occurrences
s = s.replace('Horilla Bot', 'HR Bot')
s = s.replace('&quot;HR Bot&quot;', '&quot;HR Bot&quot;')

with io.open(p, 'w', encoding='utf-8') as f:
    f.write(s)

print('Updated', p)
