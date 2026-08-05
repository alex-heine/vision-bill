import asyncpg
import json
from typing import List, Any, Optional
from src.vision_bill.provider.db.base import DatabaseProvider
from src.vision_bill.model.receipt import Receipt
from src.vision_bill.model.image import ImageInfo, TempImageInfo
from src.vision_will.config import PGSettings

class PostgresProvider(DatabaseProvider):
    def __init__(self, settings: PGSettings):
        self.settings = settings
        self._pool = None

    async def connect(self) -> None:
        if not self._pool:
            dsn = f"postgresql://{self.settings.user}:{self.settings.password}@{self.settings.host}:{self.settings.port}/{self.settings.db}"
            self._pool = await asyncpg.create_pool(dsn)

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    async def save_receipt(self, receipt: Receipt) -> None:
        data = receipt.model_dump()
        line_items = json.dumps([item.dict() for item in data['line_items']])
        taxes = json.dumps([tx.dict() for tx in data['taxes']])

        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO receipts (merchant_name, merchant_address, receipt_number, date, time, 
                                     currency, line_items, taxes, subtotal, discount_total, tax_total, 
                                     tip, total, payment_method)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (receipt_number) DO UPDATE SET
                    merchant_name = EXCLUDED.merchant_name,
                    merchant_address = EXCLUDED.merchant_address,
                    date = EXCLUDED.date,
                    time = EXCLUDED.time,
                    currency = EXCLUDED.currency,
                    line_items = EXCLUDED.line_items,
                    taxes = EXCLUDED.taxes,
                    subtotal = EXCLUDED.subtotal,
                    discount_total = EXCLUDED.discount_total,
                    tax_total = EXcluded.tax_total,
                    tip = EXcluded.tip,
                    total = EXClosed.total,
                    payment_method = EXClosed.payment_method
            ''', 
            data['merchant_name'], data['merchant_address'], data['receipt_number'],
            data['date'], data['time'], data['currency'],
            line_items, taxes, data['subtotal'], data['discount_total'], data['tax_total'],
            data['tip'], data['total'], data['payment_method'])

    async def get_receipt_by_id(self, receipt_number: str) -> Optional[Receipt]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM receipts WHERE receipt_number = $1', receipt_number)
            if not row:
                return None
            data = dict(row)
            # Handle JSON deserialization for nested fields
            data['line_items'] = json.loads(data['line_items']) if isinstance(data['line_items'], str) else data['line_items']
            data['taxes'] = json.loads(data['taxes']) if isinstance(data['taxes'], str) else data['taxes']
            return Receipt(**data)

    async def save_image_info(self, image: ImageInfo) -> None:
        data = image.model_dump()
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO images (media_type, size_bytes, content)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
            ''', data['media_type'], data['size_bytes'], data['content'])

    async def get_image_info(self, image_id: str) -> Optional[ImageInfo]:
        # Assuming 'some_identifier' exists as a placeholder if no PK is defined in model
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM images WHERE some_internal_id = $1', image_id)
            if not row:
                return None
            return ImageInfo(**dict(row))

    async def save_temp_image(self, temp_image: TempImageInfo) -> None:
        data = temp_image.model_dump()
        async with self._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO temp_images (image_id, file_path, timestamp)
                VALUES ($1, $2, $3)
                ON CONFLICT (image_id) DO UPDATE SET
                    file_path = EXCLUDED.file_path,
                    timestamp = EXCLUDED.timestamp
            ''', data['image_id'], data['file_path'], data['timestamp'])

    async def get_temp_image(self, image_id: str) -> Optional[TempImageInfo]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM temp_images WHERE image_id = $1', image_id)
            if not row:
                return None
            return TempImageInfo(**dict(row))

    async def get_tmpimage_since(self, seconds: int) -> List[TempImageInfo]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetchmany('''
                SELECT * FROM temp_images 
                WHERE timestamp < NOW() - INTERVAL '$1 seconds'
            ''', seconds)
            if not rows:
                return []
            return [TempImageInfo(**dict(r)) for r in rows]
