export async function onRequest({ params, request }) {
  const path = params.path.join("/");
  const upstream = `https://meworks.pages.dev/${path}`;
  const resp = await fetch(upstream);
  return new Response(resp.body, {
    status: resp.status,
    headers: resp.headers,
  });
}