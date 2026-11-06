from tools.tavily_tool import tavily_search
from tools.flight_tool import search_flights
from backend import run_travel_agent, render_travel_plan_pdf

# res = tavily_search("Best hotels in India")
# print(res)


# res = search_flights("Plan a 7 days Nepal trip from Bangladesh")
# print(res)

user_input = input("Enter travel request: ")

response = run_travel_agent(
    user_input=user_input,
    thread_id="test_user"
)

print("\nFINAL RESPONSE:\n")
print(response["answer"])

plan = response.get("plan")
if plan:
    print("\n[Structured Plan Detected]")
    print(f"Destination: {plan.get('destination')}")
    print(f"Duration:    {plan.get('duration')}")
    try:
        pdf_bytes = render_travel_plan_pdf(plan)
        filename = "ke-hoach-du-lich.pdf"
        with open(filename, "wb") as f:
            f.write(pdf_bytes)
        print(f"-> Xuat file PDF thanh cong: {filename}")
    except Exception as e:
        print(f"-> Khong the xuat PDF: {e}")