import re
import os

html_path = 'stitch_ui.html'
app_path = 'src/App.tsx'

with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Extract body contents
body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
if not body_match:
    print("Body not found")
    exit(1)
body_html = body_match.group(1)

# Basic JSX conversions
jsx = body_html.replace('class="', 'className="')
jsx = jsx.replace('for="', 'htmlFor="')
jsx = jsx.replace('<!--', '{/*')
jsx = jsx.replace('-->', '*/}')

# Replace style="background-image: ..." if any exists with simple style maps or just strip it.
# Actually there are no inline styles except in the <style> header which we ignored.

# Self close img and input tags
jsx = re.sub(r'<img([^>]+)(?<!/)>', r'<img\1 />', jsx)
jsx = re.sub(r'<input([^>]+)(?<!/)>', r'<input\1 />', jsx)
jsx = re.sub(r'<br([^>]*)(?<!/)>', r'<br\1 />', jsx)

# Locate the map container and inject LeafletMap
map_replacement = r'<div className="w-full h-full absolute inset-0 z-0"><LeafletMap heatmapData={heatmapData} shortestRoute={null} cleanestRoute={null} /></div>'
jsx = re.sub(r'<img className="w-full h-full object-cover[^>]+/>', map_replacement, jsx)

import_statements = """import React, { useState } from 'react';
import LeafletMap from './components/LeafletMap';

function useRealHeatmapData() {
  const [data, setData] = React.useState<any[]>([]);
  React.useEffect(() => {
    async function fetchOpenAQ() {
      try {
        const res = await fetch('https://api.openaq.org/v2/latest?coordinates=28.6139,77.2090&radius=25000&limit=100');
        const json = await res.json();
        if (json && json.results) {
          const points = json.results.map((r: any) => {
            const pm25 = r.measurements.find((m: any) => m.parameter === 'pm25')?.value || 15.0;
            const intensity = Math.min(pm25 / 150.0, 1.0);
            return [r.coordinates.latitude, r.coordinates.longitude, intensity];
          });
          setData(points);
        }
      } catch (e) {
        console.error("OpenAQ live API fetch failed:", e);
      }
    }
    fetchOpenAQ();
  }, []);
  return data;
}

function App() {
  const heatmapData = useRealHeatmapData();

  return (
    <div className="w-full h-screen relative bg-slate-900 overflow-hidden font-['Inter'] text-slate-100">
"""

footer = """
    </div>
  );
}

export default App;
"""

final_code = import_statements + jsx + footer

with open(app_path, 'w', encoding='utf-8') as f:
    f.write(final_code)

print("App.tsx rewritten successfully!")
