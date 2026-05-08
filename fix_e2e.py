import os
data = open(r'e:/Macro/Cupid/tools/e2e_test.py', 'r', encoding='utf-8').read()
lines = data.split('\n')
# Fix line 6: should be 4 opens, 4 closes
# os.path.dirname(os.path.dirname(os.path.abspath(__file__))
lines[5] = "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))"
data = '\n'.join(lines)
open(r'e:/Macro/Cupid/tools/e2e_test.py', 'w', encoding='utf-8').write(data)
print('Fixed line 6')
