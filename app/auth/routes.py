from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import oauth, utils
from app.auth import auth_router
from app.auth.models import Usuario


@auth_router.get('/suap/login')
async def suap_login(request: Request):
    return await oauth.suap.authorize_redirect(
        request, redirect_uri=request.url_for('suap_callback')
    )


@auth_router.get('/suap/callback')
async def suap_callback(request: Request, db: AsyncSession = Depends(utils.get_db)):
    token = await oauth.suap.authorize_access_token(request)

    res = await oauth.suap.get('/api/rh/eu/', token=token)
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail='erro de requisição ao suap!')

    data = res.json()

    usuario = await db.scalar(
        select(Usuario).where(
            Usuario.matricula == data.get('identificacao')
        )
    )

    if not usuario:
        usuario = Usuario(
            matricula=data.get('identificacao')
        )

    usuario.nome = data.get('nome_social') or data.get('nome_registro')
    usuario.email = data.get('email_preferencial')

    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)

    request.session['user_id'] = str(usuario.id)

    return {
        'msg': 'login realizado com sucesso!'
    }


@auth_router.post('/logout')
async def logout(request: Request):
    if request.session.get('user_id'):
        request.session.pop('user_id')

    return {
        'msg': 'logout realizado com sucesso!'
    }
