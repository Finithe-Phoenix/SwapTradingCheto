FROM freqtradeorg/freqtrade:2026.8
USER root
COPY src /lab/src
COPY configs /lab/configs
COPY scripts/freqtrade_entrypoint.py /lab/freqtrade_entrypoint.py
ENV PYTHONPATH=/lab/src
USER ftuser
ENTRYPOINT ["python", "/lab/freqtrade_entrypoint.py"]
CMD ["trade"]
