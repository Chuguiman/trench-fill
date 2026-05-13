import json
from collections import Counter

file_path = 'public/exports/5837b788-43f8-4d58-9266-a0514fca31d2.json'

with open(file_path, 'r') as f:
    data = json.load(f)

entities = data.get('entities', [])
type_counts = Counter(e['type'] for e in entities)
layer_counts = Counter(e['layer'] for e in entities)

print(f"Total entities: {len(entities)}")
print("\nEntity types:")
for t, count in type_counts.most_common():
    print(f"  {t}: {count}")

print("\nTop 20 Layers:")
for l, count in layer_counts.most_common(20):
    print(f"  {l}: {count}")

# Check some samples of TEXT and LWPOLYLINE
text_samples = [e for e in entities if e['type'] in ('TEXT', 'MTEXT')][:5]
poly_samples = [e for e in entities if e['type'] in ('LWPOLYLINE', 'POLYLINE')][:5]

print("\nText samples:")
for s in text_samples:
    print(f"  {s}")

print("\nPolyline samples:")
for s in poly_samples:
    print(f"  {s}")
