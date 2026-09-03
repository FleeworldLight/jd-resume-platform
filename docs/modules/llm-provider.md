# LLM Provider 模块

> 多模型配置 + 加密存储 + 运行时切换。

---

## 1. 数据模型

```python
# app/db/models/llm_provider.py
class LLMProvider(Base):
    __tablename__ = "llm_providers"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    provider_type: Mapped[str] = mapped_column(String(32))  # DASHSCOPE / OPENAI_COMPATIBLE
    base_url: Mapped[str | None] = mapped_column(String(512))
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    chat_model: Mapped[str | None] = mapped_column(String(128))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    is_default: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
```

---

## 2. 接口

```python
# app/api/llm_providers.py
router = APIRouter(prefix="/api/llm-providers", tags=["llm-providers"])

@router.get("", response_model=Result[list[LLMProviderResponse]])
async def list_providers(service: LLMProviderService = Depends()):
    providers = await service.list()
    return Result.ok([p.to_response() for p in providers])

@router.post("", response_model=Result[LLMProviderResponse])
@limiter.limit("5/minute")
async def create_provider(
    request: Request,
    req: LLMProviderCreateRequest,
    service: LLMProviderService = Depends(),
):
    provider = await service.create(req)
    return Result.ok(provider.to_response())

@router.put("/{provider_id}", response_model=Result[LLMProviderResponse])
async def update_provider(
    provider_id: int,
    req: LLMProviderUpdateRequest,
    service: LLMProviderService = Depends(),
):
    provider = await service.update(provider_id, req)
    return Result.ok(provider.to_response())

@router.delete("/{provider_id}", response_model=Result[None])
async def delete_provider(provider_id: int, service: LLMProviderService = Depends()):
    await service.delete(provider_id)
    return Result.ok(message="删除成功")

@router.post("/{provider_id}/test", response_model=Result[LLMTestResponse])
@limiter.limit("3/minute")
async def test_provider(
    request: Request,
    provider_id: int,
    service: LLMProviderService = Depends(),
):
    result = await service.test_connection(provider_id)
    return Result.ok(result)

@router.post("/{provider_id}/set-default", response_model=Result[None])
async def set_default_provider(provider_id: int, service: LLMProviderService = Depends()):
    await service.set_default(provider_id)
    return Result.ok(message="已设为默认")
```

---

## 3. Service 实现

```python
# app/services/llm_provider_service.py
from cryptography.fernet import Fernet

class LLMProviderService:
    SUPPORTED_TYPES = {"DASHSCOPE", "OPENAI_COMPATIBLE"}
    
    def __init__(self, db: AsyncSession, encryption_key: bytes):
        self.db = db
        self.cipher = Fernet(encryption_key)
    
    def _encrypt_api_key(self, api_key: str) -> str:
        return self.cipher.encrypt(api_key.encode()).decode()
    
    def _decrypt_api_key(self, encrypted: str) -> str:
        return self.cipher.decrypt(encrypted.encode()).decode()
    
    async def create(self, req: LLMProviderCreateRequest) -> LLMProvider:
        if req.provider_type not in self.SUPPORTED_TYPES:
            raise BusinessException(ErrorCode.LLM_PROVIDER_TYPE_UNKNOWN)
        
        provider = LLMProvider(
            name=req.name,
            provider_type=req.provider_type,
            base_url=req.base_url,
            api_key_encrypted=self._encrypt_api_key(req.api_key) if req.api_key else None,
            chat_model=req.chat_model,
            embedding_model=req.embedding_model,
            is_default=req.is_default,
            enabled=True,
        )
        
        # 如果设为默认，把其他都置为非默认
        if req.is_default:
            await self._clear_default()
        
        self.db.add(provider)
        await self.db.commit()
        return provider
    
    async def set_default(self, provider_id: int):
        provider = await self.db.get(LLMProvider, provider_id)
        if not provider:
            raise BusinessException(ErrorCode.LLM_PROVIDER_NOT_FOUND)
        
        await self._clear_default()
        provider.is_default = True
        await self.db.commit()
    
    async def _clear_default(self):
        await self.db.execute(
            update(LLMProvider)
            .where(LLMProvider.is_default == True)
            .values(is_default=False)
        )
    
    async def test_connection(self, provider_id: int) -> LLMTestResponse:
        provider = await self.db.get(LLMProvider, provider_id)
        if not provider:
            raise BusinessException(ErrorCode.LLM_PROVIDER_NOT_FOUND)
        
        api_key = self._decrypt_api_key(provider.api_key_encrypted) if provider.api_key_encrypted else None
        
        try:
            chat_model = self._create_chat_model(provider, api_key)
            response = await chat_model.ainvoke("你好")
            return LLMTestResponse(
                success=True,
                message="连接成功",
                response_preview=response.content[:100],
            )
        except Exception as e:
            return LLMTestResponse(
                success=False,
                message=f"连接失败: {str(e)}",
            )
    
    def _create_chat_model(self, provider: LLMProvider, api_key: str):
        if provider.provider_type == "DASHSCOPE":
            from langchain_community.chat_models.tongyi import ChatTongyi
            return ChatTongyi(model=provider.chat_model, dashscope_api_key=api_key)
        elif provider.provider_type == "OPENAI_COMPATIBLE":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(base_url=provider.base_url, api_key=api_key, model=provider.chat_model)
    
    def to_response(self, provider: LLMProvider) -> LLMProviderResponse:
        return LLMProviderResponse(
            id=provider.id,
            name=provider.name,
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            chat_model=provider.chat_model,
            embedding_model=provider.embedding_model,
            is_default=provider.is_default,
            enabled=provider.enabled,
            api_key_masked=self._mask_api_key(provider.api_key_encrypted),
        )
    
    def _mask_api_key(self, encrypted: str) -> str:
        if not encrypted:
            return ""
        decrypted = self._decrypt_api_key(encrypted)
        if len(decrypted) < 8:
            return "***"
        return decrypted[:4] + "***" + decrypted[-4:]
```

---

## 4. 加密

### 4.1 密钥管理

```python
# app/core/config.py
from cryptography.fernet import Fernet

class Settings(BaseSettings):
    encryption_key: str  # Fernet key, 从 .env 读取
    
    @property
    def fernet_key(self) -> bytes:
        return self.encryption_key.encode()
```

`.env`：
```
LLM_ENCRYPTION_KEY=your-generated-fernet-key
```

生成密钥：
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4.2 加密存储

API Key 加密后存数据库，前端展示时脱敏：
- 原文：只在调用 LLM 时解密
- 日志：永远不打印明文

---

## 5. 多 Provider 路由

LLMService 自动选默认：

```python
# app/services/llm_service.py
class LLMService:
    async def _get_provider(self, name: str | None = None) -> LLMProvider:
        if name:
            return await self._get_by_name(name)
        return await self._get_default()
    
    async def _get_default(self) -> LLMProvider:
        result = await self.db.execute(
            select(LLMProvider)
            .where(LLMProvider.is_default == True)
            .where(LLMProvider.enabled == True)
        )
        provider = result.scalar_one_or_none()
        if not provider:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_DISABLED,
                "未配置默认 LLM Provider，请在设置页配置"
            )
        return provider
```

---

## 6. 测试

```python
# tests/unit/services/test_llm_provider_service.py
def test_encrypt_decrypt_api_key():
    service = LLMProviderService(db, Fernet.generate_key())
    original = "sk-test-key-1234567890"
    encrypted = service._encrypt_api_key(original)
    assert encrypted != original
    assert service._decrypt_api_key(encrypted) == original

def test_mask_api_key():
    service = LLMProviderService(db, Fernet.generate_key())
    encrypted = service._encrypt_api_key("sk-test-key-1234567890")
    masked = service._mask_api_key(encrypted)
    assert "sk-" in masked
    assert "1234567890" in masked
    assert "key" not in masked  # 中间部分被隐藏

@pytest.mark.asyncio
async def test_set_default_clears_others(provider_service):
    # 创建 2 个 provider
    p1 = await provider_service.create(...)
    p2 = await provider_service.create(...)
    
    # 把 p2 设为默认
    await provider_service.set_default(p2.id)
    
    # 验证 p1 不是默认了
    assert p1.is_default == False
    assert p2.is_default == True
```

---

## 7. 面试讲点

1. **"API Key 怎么存？"**
   > Fernet 对称加密，密钥从环境变量读，不进数据库。前端展示脱敏（只显首尾4 位）。

2. **"多 Provider 切换怎么做的？"**
   > 数据库存多个 Provider 配置，一个标记为默认。LangChain 抽象了下层，根据 provider_type 选对应的 ChatModel 实现。

3. **"默认模型切换为什么能立即生效？"**
   > 每次 LLM 调用都从数据库读默认 Provider，不缓存。改默认模型后下次调用就生效。

4. **"测试连接接口怎么实现的？"**
   > 实例化 ChatModel 发一条简单消息（"你好"），成功返回响应预览，失败返回错误信息。