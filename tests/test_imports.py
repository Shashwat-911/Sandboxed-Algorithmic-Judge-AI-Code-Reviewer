import io
from contextlib import contextmanager
from unittest.mock import patch
import httpx
import pytest
from atf import archive, repository
from test_atf import api, zipped, wait_report


def test_large_zip_over_old_limit(api):
    data = zipped({'repo/main.py':'pass', 'repo/assets/video.bin':b'x'*(11*1024*1024)})
    assert len(data) > 10*1024*1024
    response=api.post('/api/projects',files={'file':('large.zip',data)})
    assert response.status_code==202
    report=wait_report(api,response.json()['id'])['report']
    assert report['summary']['files']==1
    assert report['skipped_files']==['repo/assets/video.bin']
    assert api.get('/api/limits').json()['upload_mb']==100


def test_filtered_large_files_and_source_budget(monkeypatch):
    monkeypatch.setattr(archive,'MAX_FILE',10)
    files,skipped=archive.read_archive(io.BytesIO(zipped({'main.py':'pass','huge.py':'x'*11})))
    assert files=={'main.py':'pass'} and skipped==['huge.py']
    monkeypatch.setattr(archive,'MAX_SOURCE',3)
    with pytest.raises(ValueError,match='Supported source'): archive.read_archive(zipped({'main.py':'pass'}))

@pytest.mark.parametrize('url',[
    'http://github.com/a/b','https://localhost/a/b','https://github.com.evil.com/a/b',
    'https://user:password@github.com/a/b','https://github.com:443/a/b',
    'https://github.com/a/b?x=1','https://github.com/a/b#x','https://github.com/a/b/tree/main',
    'file:///tmp/repo','https://github.com/a/%2e%2e',
])
def test_repository_url_restrictions(url):
    with pytest.raises(ValueError): repository.parse_repository(url)


def test_repository_refs():
    assert repository.parse_repository('https://github.com/owner/repo.git/')==('owner','repo','HEAD')
    assert repository.parse_repository('https://github.com/a/b','feature/upload')[-1]=='feature/upload'
    with pytest.raises(ValueError): repository.parse_repository('https://github.com/a/b','../main')


def mock_download(monkeypatch, handler):
    real_client=httpx.Client
    monkeypatch.setattr(repository.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))


def test_repository_download_stream(monkeypatch):
    data=zipped({'repo/main.py':'pass'})
    def handler(request):
        assert request.url.host=='codeload.github.com'
        return httpx.Response(200,content=data)
    mock_download(monkeypatch,handler)
    with repository.repository_archive('https://github.com/a/b','main') as (stream,source):
        assert archive.read_archive(stream)[0]=={'main.py':'pass'}
        assert source=={'kind':'github','url':'https://github.com/a/b','ref':'main'}
    assert stream.closed

@pytest.mark.parametrize('status,message',[(404,'not found'),(403,'rate-limited'),(429,'rate-limited'),(302,'redirected'),(500,'Could not download')])
def test_repository_download_errors(monkeypatch,status,message):
    mock_download(monkeypatch,lambda request:httpx.Response(status,headers={'location':'http://localhost/private'}))
    with pytest.raises(ValueError,match=message):
        with repository.repository_archive('https://github.com/a/b'): pass


def test_repository_stream_size_limit(monkeypatch):
    monkeypatch.setattr(repository,'MAX_UPLOAD',10)
    class Chunks(httpx.SyncByteStream):
        def __iter__(self): yield b'x'*11
    mock_download(monkeypatch,lambda request:httpx.Response(200,stream=Chunks()))
    with pytest.raises(ValueError,match='exceeds'):
        with repository.repository_archive('https://github.com/a/b'): pass


def test_repository_endpoint_and_reservation(api,monkeypatch):
    import main
    @contextmanager
    def download(url,ref):
        yield io.BytesIO(zipped({'repo/main.py':'pass'})), {'kind':'github','url':url,'ref':ref or 'HEAD'}
    monkeypatch.setattr(main,'repository_archive',download)
    response=api.post('/api/repositories',json={'url':'https://github.com/a/b','ref':'main'})
    assert response.status_code==202
    row=wait_report(api,response.json()['id'])
    assert row['report']['source']['ref']=='main'
    assert 'github.com/a/b' in api.get(f"/api/projects/{row['id']}/report").text
    assert api.post('/api/repositories',json={'url':'http://localhost'}).status_code==400
    @contextmanager
    def bad_download(url,ref):
        raise ValueError('download failed')
        yield
    monkeypatch.setattr(main,'repository_archive',bad_download)
    for _ in range(7):
        assert api.post('/api/repositories',json={'url':'https://github.com/a/b'}).status_code==400
    # Repeated failures must not leak queue slots.
    response=api.post('/api/demo')
    assert response.status_code==202
    wait_report(api,response.json()['id'])


def test_runner_large_project_skips_without_docker():
    from atf.runner import execute_tests
    with patch('atf.runner.docker.from_env') as docker:
        report=execute_tests({'test_a.py':'pass', **{f'{i}.py':'' for i in range(2001)}},True)
    assert report['status']=='skipped'
    docker.assert_not_called()
