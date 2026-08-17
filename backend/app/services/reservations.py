from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool

def quantize_money(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month.
    """
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        tz_row = (await session.execute(
            text("""
                SELECT timezone
                FROM properties
                WHERE id = :property_id AND tenant_id = :tenant_id
            """),
            {"property_id": property_id, "tenant_id": tenant_id}
        )).fetchone()

        if tz_row is None:
            raise LookupError(f"Property {property_id} not found for tenant {tenant_id}")

        # Naive datetimes compare against check_in_date (TIMESTAMPTZ) as UTC,
        # pulling bookings into the wrong month for non-UTC properties.
        tz = ZoneInfo(tz_row.timezone)
        start_date = datetime(year, month, 1, tzinfo=tz)
        if month < 12:
            end_date = datetime(year, month + 1, 1, tzinfo=tz)
        else:
            end_date = datetime(year + 1, 1, 1, tzinfo=tz)

        row = (await session.execute(
            text("""
                SELECT
                    SUM(total_amount) as total_revenue,
                    COUNT(*) as reservation_count
                FROM reservations
                WHERE property_id = :property_id
                AND tenant_id = :tenant_id
                AND check_in_date >= :start_date
                AND check_in_date < :end_date
            """),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_date": start_date,
                "end_date": end_date,
            }
        )).fetchone()

    total_revenue = Decimal(str(row.total_revenue)) if row.total_revenue is not None else Decimal("0")

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "month": month,
        "year": year,
        "timezone": tz_row.timezone,
        "total": quantize_money(total_revenue),
        "currency": "USD",
        "count": row.reservation_count,
    }

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        query = text("""
            SELECT
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    # total_revenue is NULL when the tenant has no reservations for this property.
    total_revenue = Decimal(str(row.total_revenue)) if row.total_revenue is not None else Decimal("0")

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": quantize_money(total_revenue),
        "currency": "USD",
        "count": row.reservation_count
    }
