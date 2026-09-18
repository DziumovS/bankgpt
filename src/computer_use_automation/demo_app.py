import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="Legacy Credit Union Demo")

MEMBERS = {
    "12345": {"name": "Demo Member", "savings": "$1,427.52"},
    "67890": {"name": "Second Member", "savings": "$315.08"},
}

PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Legacy Credit Union Console</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 32px; background: #f3f3f3; }
    table { border-collapse: collapse; background: white; }
    td { border: 1px solid #777; padding: 8px; }
    .panel { background: white; border: 1px solid #777; padding: 18px; width: 620px; }
  </style>
</head>
<body>
  <h1>Member Servicing Console</h1>
  <div class="panel">
    <form method="post" action="/member/search">
      <table>
        <tr><td><label for="member-number">Member Number</label></td>
            <td><input id="member-number" name="member_id" autocomplete="off"></td></tr>
        <tr><td colspan="2"><button type="submit">Search Member</button></td></tr>
      </table>
    </form>
  </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


@app.post("/member/search", response_class=HTMLResponse)
def search_member(member_id: str = Form(...)) -> str:
    member = MEMBERS.get(member_id)
    if member is None:
        return """
        <html><head><title>Member Search</title></head><body>
        <h1>Member Search Result</h1>
        <p>Member not found</p>
        <a href="/">Return to search</a>
        </body></html>
        """
    return f"""
    <html><head><title>Member Details</title></head><body>
    <h1>Member Details</h1>
    <table>
      <tr><td>Member Number</td><td>{member_id}</td></tr>
      <tr><td>Member Name</td><td>{member['name']}</td></tr>
      <tr><td>Savings Balance</td><td><span role="status" aria-label="Savings Balance">{member['savings']}</span></td></tr>
    </table>
    <p>Account details loaded</p>
    <a href="/">New search</a>
    </body></html>
    """


def run() -> None:
    uvicorn.run("computer_use_automation.demo_app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
