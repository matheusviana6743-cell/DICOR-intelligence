from app import app, PRODUCTS, db, now
from security import harden
from flask import request, redirect, url_for

# MODO TESTE: todos os produtos ficam gratuitos e nenhum pagamento é criado.
for _product in PRODUCTS.values():
    if _product.get("type") == "fixed":
        _product["price"] = 0.0
    else:
        _product["min"] = 0.0
        _product["max"] = 0.0

@app.before_request
def free_test_checkout():
    if request.method != "POST" or not request.path.startswith("/checkout/"):
        return None
    token = request.path.rsplit("/", 1)[-1]
    con = db()
    order = con.execute("SELECT * FROM orders WHERE token=?", (token,)).fetchone()
    if not order:
        con.close()
        return None
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    phone = "".join(c for c in request.form.get("phone", "") if c.isdigit())
    if not name or not email or not phone:
        con.close()
        return None
    con.execute(
        "UPDATE orders SET customer_name=?, customer_email=?, customer_phone=?, price=0, price_min=0, price_max=0, status=?, payment_status=?, updated_at=? WHERE id=?",
        (name, email, phone, "Em teste", "Não necessário", now(), order["id"])
    )
    con.commit()
    con.close()
    return redirect(url_for("order_page", token=token))

app = harden(app)
