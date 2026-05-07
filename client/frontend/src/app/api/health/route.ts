const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
  const res = await fetch(`${BACKEND}/api/health`);
  const data = await res.json();
  return Response.json(data);
}
