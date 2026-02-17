# Shams Frontend

React + TypeScript frontend for Shams fantasy basketball analysis tool.

## Features

- **Player Search** - Search and view comprehensive player statistics
- **Waiver Wire** - Browse available players with minute trends and 9-cat stats
- **Matchup Projection** - View current matchup with projected outcomes
- **Yahoo OAuth** - Secure authentication with Yahoo Fantasy Sports
- **Color-coded Stats** - Visual indicators matching CLI thresholds
- **Responsive Design** - Works on desktop and mobile

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Fast build tool and dev server
- **Tailwind CSS** - Utility-first styling
- **React Router** - Client-side routing
- **Axios** - HTTP client

## Development Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Create `.env` file:
```bash
VITE_API_URL=http://localhost:8000
```

3. Run development server:
```bash
npm run dev
```

4. Access at `http://localhost:5173`

## Docker Development

```bash
# From project root
docker-compose up frontend
```

## Production Build

```bash
npm run build
```

This creates optimized production files in `dist/` directory.

## Docker Production

```bash
# From project root
docker-compose -f docker-compose.prod.yml up -d
```

Frontend will be served by nginx on port 80.

## Project Structure

```
frontend/
├── src/
│   ├── components/     # Reusable UI components
│   │   ├── StatCell.tsx
│   │   ├── PlayerTable.tsx
│   │   ├── Layout.tsx
│   │   └── AuthCallback.tsx
│   ├── pages/          # Page components
│   │   ├── Home.tsx
│   │   ├── Login.tsx
│   │   ├── PlayerSearch.tsx
│   │   ├── WaiverWire.tsx
│   │   └── Matchup.tsx
│   ├── services/       # API client
│   │   └── api.ts
│   ├── types/          # TypeScript types
│   │   └── api.ts
│   ├── utils/          # Utility functions
│   │   └── statColors.ts
│   ├── App.tsx         # Main app with routing
│   ├── main.tsx        # Entry point
│   └── index.css       # Global styles
├── public/             # Static assets
├── index.html          # HTML template
└── package.json
```

## Color Coding System

Stats are color-coded to match CLI thresholds:
- **Green** - Excellent value
- **Yellow** - Solid value
- **Gray** - Low/minimal value
- **Red** - Negative/poor value

Thresholds are configurable in `src/utils/statColors.ts`.

## API Integration

The frontend communicates with the backend via REST API:
- Session-based authentication with cookies
- Automatic retry and error handling
- Type-safe request/response models

## Contributing

1. Follow existing code style
2. Add TypeScript types for all components
3. Use Tailwind CSS for styling
4. Keep components small and reusable

