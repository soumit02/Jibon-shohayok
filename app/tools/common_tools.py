"""Tools that do not need any user data: calculator, weather, web search."""
import ast
import operator

import httpx

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def safe_eval(expression: str) -> float:
    """Evaluates + - * / // % and brackets only. No names, no function calls."""
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        raise ValueError("Only simple arithmetic is allowed.")

    return walk(ast.parse(expression.replace(",", "").strip(), mode="eval"))


def make_calculator_tool():
    from crewai.tools import tool

    @tool("calculator")
    def calculator(expression: str) -> str:
        """Calculate a simple arithmetic expression such as '3*1200 + 450'. ALWAYS use this for any addition or multiplication of costs."""
        try:
            value = safe_eval(expression)
            return str(int(value)) if float(value).is_integer() else str(round(value, 2))
        except Exception as exc:
            return f"Calculation error: {exc}"

    return calculator


def make_weather_tool():
    from crewai.tools import tool
    state = {"calls": 0}  # a new tool is built for every crew run, so this counter is per run

    @tool("weather_forecast")
    def weather_forecast(place: str) -> str:
        """Get a 7 day weather forecast (temperature and rain) for a place, for example 'Sylhet' or 'Cox's Bazar'. Use it at most once."""
        state["calls"] += 1
        if state["calls"] > 1:
            return "LIMIT_REACHED: weather was already checked. Do not call this tool again."
        try:
            geo = httpx.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": place, "count": 1}, timeout=10,
            ).json()
            if not geo.get("results"):
                return f"Place '{place}' was not found."
            spot = geo["results"][0]
            fc = httpx.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": spot["latitude"], "longitude": spot["longitude"],
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "forecast_days": 7, "timezone": "Asia/Dhaka",
                }, timeout=10,
            ).json()["daily"]
            lines = [
                f"{d}: {lo}-{hi} C, rain {rain} mm"
                for d, lo, hi, rain in zip(fc["time"], fc["temperature_2m_min"], fc["temperature_2m_max"], fc["precipitation_sum"])
            ]
            return f"Forecast for {spot['name']}:\n" + "\n".join(lines)
        except Exception as exc:
            return f"Weather service is unavailable right now ({exc.__class__.__name__})."

    return weather_forecast


def make_web_search_tool():
    from crewai.tools import tool
    state = {"calls": 0}  # only ONE web search per crew run: the search is slow and eats the model's token limit

    @tool("web_search")
    def web_search(query: str) -> str:
        """Search the web ONCE for current travel information (places, ticket info, hotel ideas). Returns the top 3 short results. Use it at most once."""
        state["calls"] += 1
        if state["calls"] > 1:
            return "LIMIT_REACHED: web search was already used. Do not search again; say the price is not available."
        try:
            from ddgs import DDGS
        except ImportError:
            return "Web search is not installed on this server."
        try:
            try:
                engine = DDGS(timeout=8)
            except TypeError:  # older/newer ddgs versions may not have the timeout argument
                engine = DDGS()
            rows = engine.text(query, max_results=3)
            if not rows:
                return "No web results found."
            return "\n\n".join(f"{r.get('title')}\n{str(r.get('body'))[:250]}\n{r.get('href')}" for r in rows)
        except Exception as exc:
            return f"Web search failed ({exc.__class__.__name__}). Do not guess; say the information is not available."

    return web_search
